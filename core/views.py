from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from datetime import timedelta, date
from django.http import JsonResponse
from .models import Todo as Task, Profile, Badge, UserBadge, Team, User, StudyPlan
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from itertools import groupby
from .ai_service import call_groq_api, generate_study_plan_with_ai
from django.db.models import Q
import re
import markdown as md


from .ai_service import (
    get_task_category_with_ai, 
    get_sub_tasks_with_ai, 
    get_task_difficulty_with_ai, 
    get_time_estimate_with_ai
)


def parse_plan_days(plan_text):
    """
    Returns list of dicts: [{'day': 1, 'title': 'Title', 'content': '...'}, ...]
    Robustly extracts blocks that start with "## Day N: Title" (case-insensitive).
    Works with the AI output format your app expects.
    """
    pattern = r'##\s*Day\s*(\d+)\s*:?\s*([^\n\r]+)\s*(.*?)(?=(?:##\s*Day\s*\d+\s*:)|\Z)'
    matches = re.findall(pattern, plan_text, flags=re.IGNORECASE | re.DOTALL)
    days = []
    for num_str, title, content in matches:
        try:
            num = int(num_str)
        except ValueError:
            continue
        days.append({
            'day': num,
            'title': title.strip(),
            'content': content.strip()
        })
    days.sort(key=lambda d: d['day'])
    return days




def award_xp_and_level_up(user, task_difficulty):
    """Awards XP based on task difficulty and handles level ups."""
    profile, created = Profile.objects.get_or_create(user=user)
    
    xp_map = {'Easy': 15, 'Moderate': 25, 'Hard': 40}
    xp_to_add = xp_map.get(task_difficulty, 25)
    
    profile.xp += xp_to_add
    
    xp_for_next_level = profile.level * 100
    if profile.xp >= xp_for_next_level:
        profile.level += 1
        profile.xp -= xp_for_next_level 
    
    profile.save()
    


def check_and_award_badges(user, completed_task):
    """Checks all badge conditions and awards them if met."""
    profile, created = Profile.objects.get_or_create(user=user)
    today = timezone.now().date()

   
    if completed_task.difficulty == 'Hard':
        hard_tasks_count = Task.objects.filter(user=user, status='COMPLETED', difficulty='Hard').count()
        if hard_tasks_count >= 5:
            badge, created = Badge.objects.get_or_create(name="Giant Slayer ⚔️", description="Complete 5 'Hard' difficulty tasks.")
            UserBadge.objects.get_or_create(user=user, badge=badge)

   
    task_age = (completed_task.datecompleted.date() - completed_task.created.date()).days
    if task_age >= 3:
        badge, created = Badge.objects.get_or_create(name="Phoenix 🔥", description="Complete a task that was over 3 days old.")
        UserBadge.objects.get_or_create(user=user, badge=badge)

    
    if completed_task.datecompleted.weekday() in [5, 6]: 
        tasks_on_this_day = Task.objects.filter(user=user, status='COMPLETED', datecompleted__date=completed_task.datecompleted.date()).count()
        if tasks_on_this_day >= 3:
            badge, created = Badge.objects.get_or_create(name="Weekend Warrior 🤺", description="Complete 3 or more tasks on a weekend day.")
            UserBadge.objects.get_or_create(user=user, badge=badge)

   
    completion_time = completed_task.datecompleted.time()
    
    
    if completion_time < timezone.datetime.strptime('09:00', '%H:%M').time():
        if profile.last_early_bird_date == today - timedelta(days=1):
            profile.early_bird_streak += 1
        else:
            profile.early_bird_streak = 1
        profile.last_early_bird_date = today
        if profile.early_bird_streak >= 3:
            badge, created = Badge.objects.get_or_create(name="Early Bird 🦉", description="Complete your first task before 9 AM for 3 days in a row.")
            UserBadge.objects.get_or_create(user=user, badge=badge)
 
    if completion_time > timezone.datetime.strptime('22:00', '%H:%M').time():
        if profile.last_night_owl_date == today - timedelta(days=1):
            profile.night_owl_streak += 1
        else:
            profile.night_owl_streak = 1
        profile.last_night_owl_date = today
        if profile.night_owl_streak >= 3:
            badge, created = Badge.objects.get_or_create(name="Night Owl 🌙", description="Complete a task after 10 PM for 3 days in a row.")
            UserBadge.objects.get_or_create(user=user, badge=badge)

    profile.save()



@login_required
def create_study_plan_view(request):
    if request.method == 'POST':
        user = request.user
        subject = request.POST.get('subject')
        goal = request.POST.get('goal')
        
        try:
            duration_days = int(request.POST.get('duration_days', 7))
            if not (1 <= duration_days <= 90):
                messages.error(request, "Duration must be between 1 and 90 days.")
                return render(request, 'core/create_study_plan.html')
        except (ValueError, TypeError):
             messages.error(request, "Invalid duration entered.")
             return render(request, 'core/create_study_plan.html')

        if subject and goal:
            plan_text = generate_study_plan_with_ai(subject, goal, duration_days)
            
            if not plan_text or "Could not generate" in plan_text:
                messages.error(request, "The AI failed to generate a plan. Please try again.")
                return render(request, 'core/create_study_plan.html')

            
            today = timezone.now().date()
            end_date_calc = today + timedelta(days=duration_days - 1)

            new_plan = StudyPlan.objects.create(
                user=user, 
                subject=subject, 
                goal=goal,
                duration_days=duration_days, 
                generated_plan=plan_text,
                start_date=today,      
                end_date=end_date_calc, 
                is_active=True
            )
            
            messages.success(request, "Your AI plan has been generated!")
            return redirect('view_study_plan', plan_id=new_plan.id) 
        else:
            messages.error(request, "Please fill in all fields.")
            
    return render(request, 'core/create_study_plan.html')


@login_required
def view_study_plan_view(request, plan_id):
    plan = get_object_or_404(StudyPlan, id=plan_id, user=request.user)

    plan_structure = []
    days = parse_plan_days(plan.generated_plan)

    for d in days:
        
        lines = d['content'].splitlines()
        tasks = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith(('-', '*')) or re.match(r'^\d+\.', line):
            
                task_text = re.sub(r'^[\-\*\d\.\s]+', '', line).strip()
                if task_text:
                    processed_line = re.sub(r'\*\*(.*?)\*\*', r'<strong style="color: var(--accent-color);">\1</strong>', task_text)
                    processed_line = re.sub(r'\*(.*?)\*', r'<em class="text-secondary" style="font-weight: 500;">\1</em>', processed_line)
                    processed_line = re.sub(r'\_(.*?)\_', r'<em class="text-secondary" style="font-weight: 500;">\1</em>', processed_line)
                    tasks.append(processed_line)
        if tasks:
            pretty_title = f"Day {d['day']} {d['title']}"
            plan_structure.append((pretty_title, tasks))

    context = {
        'plan': plan,
        'plan_structure': plan_structure
    }
    return render(request, 'core/view_study_plan.html', context)


@login_required
def personal_dashboard_view(request):
    user = request.user
    profile, created = Profile.objects.get_or_create(user=user)
    today = timezone.now().date()
    
    # Active plan
    active_plan = StudyPlan.objects.filter(user=user, is_active=True).first()

    # Base queries
    personal_tasks_query = Q(user=user, team=None, status__in=['INBOX', 'ACTIVE'])
    team_tasks_query = Q(assignee=user, team__isnull=False, status__in=['INBOX', 'ACTIVE'])
    
   
    plan_tasks_today_or_upcoming = Q()
    if active_plan:
        plan_tasks_today_or_upcoming |= Q(study_plan=active_plan, scheduled_date=today, status__in=['INBOX', 'ACTIVE'])
        next_plan_task = Task.objects.filter(study_plan=active_plan, status__in=['INBOX', 'ACTIVE'], scheduled_date__gte=today).order_by('scheduled_date').first()
        if next_plan_task:
            plan_tasks_today_or_upcoming |= Q(pk=next_plan_task.pk)
    
    all_my_tasks = Task.objects.filter(
        personal_tasks_query | team_tasks_query | plan_tasks_today_or_upcoming
    ).order_by('created').distinct()
    
  
    show_mood = bool(request.session.pop('show_mood_prompt', False))
    suppress_auto = bool(request.session.pop('suppress_auto_activate', False))

   
    active_task = all_my_tasks.filter(status='ACTIVE').first()

    if not active_task:
        if not show_mood and not suppress_auto:
            
            if active_plan:
                next_plan = Task.objects.filter(study_plan=active_plan, status__in=['INBOX', 'ACTIVE']).order_by('scheduled_date','created').first()
                if next_plan:
                    active_task = next_plan
        
            if not active_task:
                active_task = all_my_tasks.filter(status='INBOX').order_by('created').first()
                if active_task:
                    active_task.status = 'ACTIVE'
                    active_task.save()
        else:
           
            active_task = None

    pending_tasks = all_my_tasks.filter(status='INBOX')
    can_add_task = True
    xp_for_next_level = profile.level * 100

    context = {
        'active_task': active_task,
        'pending_tasks': pending_tasks,
        'profile': profile,
        'can_add_task': can_add_task,
        'xp_for_next_level': xp_for_next_level,
       
        'show_mood': show_mood,
        
        'show_add_forms': True,
    }
    return render(request, 'core/main.html', context)

@login_required
def createtodo_ai(request):
    if request.method == 'POST':
        user = request.user
        
        user_sentence = request.POST.get('magic_input')
        if user_sentence:
            category = get_task_category_with_ai(user_sentence)
            difficulty = get_task_difficulty_with_ai(user_sentence)
            time_estimate = get_time_estimate_with_ai(user_sentence, difficulty)
            sub_tasks_list = get_sub_tasks_with_ai(user_sentence) 

            new_task = Task.objects.create(
                user=user, 
                title=user_sentence, 
                category=category, 
                difficulty=difficulty,
                time_estimate_minutes=time_estimate, 
                sub_tasks=sub_tasks_list,
                status='INBOX',
                team=None,
                memo='' 
            )
            messages.success(request, f"AI Task '{new_task.title}' added to your inbox!")
            
            if not Task.objects.filter(user=user, status='ACTIVE', team=None).exists():
                new_task.status = 'ACTIVE' 
                new_task.save()
            
    return redirect('personal_dashboard')


@login_required
def add_task_manual(request):
    if request.method == 'POST':
        user = request.user
        
        
        title = request.POST.get('title')
        if title:
            new_task = Task.objects.create(user=user, title=title, status='INBOX', memo='')
            
            if not Task.objects.filter(user=user, status='ACTIVE', team=None).exists():
                new_task.status = 'ACTIVE'
                new_task.save()
            
    return redirect('personal_dashboard')




@login_required
def complete_task(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    
    can_complete = False
    if task.team is None and task.user == request.user: 
        can_complete = True
    elif task.assignee == request.user: 
        can_complete = True
    elif task.team is not None and request.user == task.team.owner: 
        can_complete = True

    if not can_complete:
        messages.error(request, "You do not have permission to complete this task.")
        if task.team:
            return redirect('team_dashboard', team_id=task.team.id)
        return redirect('personal_dashboard')

    task.status = 'COMPLETED'
    task.datecompleted = timezone.now()
    
    if task.team and not task.assignee:
        task.assignee = request.user

    task.save()
    
    award_xp_and_level_up(request.user, task.difficulty)
    check_and_award_badges(request.user, task)
    
    messages.success(request, f"Task '{task.title}' completed!")
    
   
    request.session['show_mood_prompt'] = True
        
    if task.team:
        return redirect('team_dashboard', team_id=task.team.id)
    else:
        return redirect('personal_dashboard')


@login_required
def delete_task(request, task_id):
    task = get_object_or_404(Task, id=task_id)
   
    can_delete = False
    
    if task.team is None and task.user == request.user:
        can_delete = True
  
    elif task.team is not None and request.user == task.team.owner:
        can_delete = True
    
    elif task.team is not None and task.assignee == request.user:
        can_delete = True

    if can_delete:
        task.delete()
        messages.success(request, f"Task '{task.title}' has been deleted.")
      
        request.session['show_mood_prompt'] = True
    else:
        messages.error(request, "You do not have permission to delete this task.")

    if task.team:
        return redirect('team_dashboard', team_id=task.team.id)
    else:
        return redirect('personal_dashboard')


@login_required
def snooze_task(request, task_id):
    task = get_object_or_404(Task, id=task_id, user=request.user)
    task.status = 'INBOX'
    task.snoozed_until = timezone.now() + timedelta(hours=1)
    task.save()
   
    next_task = Task.objects.filter(user=request.user, status='INBOX').exclude(id=task_id).order_by('created').first()
    if next_task:
        pass

    request.session['show_mood_prompt'] = True
    return redirect('personal_dashboard')

@login_required
def start_task_timer(request, task_id):
    if request.method == 'POST':
        task = get_object_or_404(Task, id=task_id, user=request.user)
        task.timer_start_time = timezone.now()
        task.timer_seconds_remaining = task.time_estimate_minutes * 60
        task.save()
        return JsonResponse({'status': 'ok', 'seconds': task.timer_seconds_remaining})
    return JsonResponse({'status': 'error'}, status=400)


@login_required
def add_time_to_timer(request, task_id):
    if request.method == 'POST':
        task = get_object_or_404(Task, id=task_id, user=request.user)
        if task.timer_seconds_remaining is not None:
            task.timer_seconds_remaining += 5 * 60 
            task.save()
            return JsonResponse({'status': 'ok', 'seconds': task.timer_seconds_remaining})
    return JsonResponse({'status': 'error'}, status=400)


@login_required
def task_history_view(request):
    completed_tasks = Task.objects.filter(user=request.user, status='COMPLETED').order_by('-datecompleted')
    
    grouped_tasks = {}
    for date, tasks in groupby(completed_tasks, key=lambda task: task.datecompleted.date()):
        grouped_tasks[date] = list(tasks)
        
    context = {'grouped_tasks': grouped_tasks}
    return render(request, 'core/history.html', context)

@login_required
def reset_history_view(request):
    if request.method == 'POST':
        Task.objects.filter(user=request.user, status='COMPLETED').delete()
        messages.success(request, "Your task history has been successfully cleared!")
    return redirect('task_history')

@login_required
def suggest_task_by_mood(request, difficulty):
    user = request.user
    
  
    suggested_task = Task.objects.filter(
        user=user, 
        status='INBOX', 
        difficulty=difficulty
    ).order_by('created').first()

    # Fallback logic
    if not suggested_task:
        suggested_task = Task.objects.filter(user=user, status='INBOX').order_by('created').first()

 
    if suggested_task:
        
        suggested_task.status = 'ACTIVE'
        suggested_task.save()
        messages.success(request, f"New task activated: '{suggested_task.title}'")
    else:
        messages.error(request, "No pending tasks found to activate.")
        
    return redirect('personal_dashboard')

@login_required
def relax_mode_view(request):
    """
    Jab user ka kaam karne ka mann na ho, to AI se suggestions maangta hai.
    """
   
    prompt = """
    I have zero motivation to work right now. I feel completely burnt out. 
    Suggest 5 simple, actionable, and very quick (under 10 minutes) activities to refresh my mind.
    Examples could be: taking a short walk, listening to a song, simple breathing exercises, drinking water, or stretching.
    Return ONLY a bulleted or numbered list of these suggestions. Do not add any extra text before or after the list.
    """
    
    
    ai_response = call_groq_api(prompt)
    
    
    suggestions = [line.strip("- ").strip() for line in ai_response.splitlines() if line.strip()]

   
    if not suggestions:
        suggestions = [
            "Take a 10-minute walk outside.",
            "Listen to one of your favorite songs.",
            "Do a simple 5-minute breathing exercise.",
            "Drink a full glass of water.",
            "Stretch your arms and back for a minute."
        ]

    context = {
        'suggestions': suggestions
    }
    return render(request, 'core/relax_mode.html', context)



@login_required
def team_list_view(request):
    """
    User jin teams ka member hai, unki list dikhata hai.
    """
  
    teams = request.user.teams.all()
    context = {
        'teams': teams
    }
    return render(request, 'core/team_list.html', context)


@login_required
def create_team_view(request):
    """
    Nayi team banane ka form handle karta hai.
    """
    if request.method == 'POST':
        team_name = request.POST.get('team_name')
        if team_name:
          
            team = Team.objects.create(name=team_name, owner=request.user)
            
            team.members.add(request.user)
            messages.success(request, f"Team '{team.name}' created successfully!")
            
            return redirect('team_list') # 
            
    return render(request, 'core/create_team.html')



@login_required
def team_dashboard_view(request, team_id):
    team = get_object_or_404(Team, id=team_id)
    
    if request.user not in team.members.all():
        messages.error(request, "You are not authorized to view this team.")
        return redirect('team_list')

    
    my_assigned_tasks = Task.objects.filter(
        team=team, 
        assignee=request.user, 
        status__in=['INBOX', 'ACTIVE']
    ).order_by('created')
    
    
    other_team_tasks = Task.objects.filter(
        team=team, 
        status__in=['INBOX', 'ACTIVE']
    ).exclude(
        assignee=request.user
    ).order_by('created')
    
  
    today = timezone.now().date()
    completed_today = Task.objects.filter(
        team=team, 
        status='COMPLETED',
        datecompleted__date=today  
    ).order_by('-datecompleted')

    members = team.members.all()

    context = {
        'team': team,
        'my_assigned_tasks': my_assigned_tasks,
        'other_team_tasks': other_team_tasks,
        'completed_today': completed_today, 
        'members': members
    }
    return render(request, 'core/team_dashboard.html', context)

@login_required
def invite_member_view(request, team_id):
    team = get_object_or_404(Team, id=team_id)
    
    
    if request.method == 'POST' and request.user == team.owner:
        email = request.POST.get('email')
        try:
            user_to_add = User.objects.get(email=email)
            if user_to_add in team.members.all():
                messages.warning(request, f"{user_to_add.username} is already in the team.")
            else:
                team.members.add(user_to_add)
                messages.success(request, f"{user_to_add.username} has been added to the team.")
        except User.DoesNotExist:
            messages.error(request, "User with this email does not exist.")
    else:
        messages.error(request, "Only the team owner can invite members.")
        
    return redirect('team_dashboard', team_id=team.id)



@login_required
def add_plan_day_tasks_view(request, plan_id, day_str):
    """
    Adds tasks for a specific day from the plan to the user's main list.
    - Robustly parses different Day header styles.
    - Ensures required NOT NULL fields are provided (memo, category, etc).
    - Sets session['suppress_auto_activate'] to avoid immediate activation on dashboard.
    """
    if request.method != 'POST':
        return redirect('view_study_plan', plan_id=plan_id)

    user = request.user
    plan = get_object_or_404(StudyPlan, id=plan_id, user=user)

    try:
        day_num_str = re.findall(r'\d+', day_str)[0]
        day_index = int(day_num_str) - 1
    except (IndexError, ValueError, TypeError):
        messages.error(request, "Invalid day format.")
        return redirect('view_study_plan', plan_id=plan.id)

    text = plan.generated_plan or ""

   
    header_pattern = re.compile(
        r'(?:^|\n)(?P<header>(?:##\s*Day\s*\d+\s*:?.*?)|(?:\*\*\s*Day\s*\d+\s*.*?\*\*))\s*(?:\n|$)',
        flags=re.IGNORECASE
    )
    headers = list(header_pattern.finditer(text))

    day_sections = []
    if headers:
        for i, m in enumerate(headers):
            start = m.end()
            end = headers[i+1].start() if i+1 < len(headers) else len(text)
            header_text = m.group('header').strip()
            content = text[start:end].strip()
            day_sections.append((header_text, content))
    else:
       
        fallback = re.split(r'(?:##\s*Day\s+\d+|^\*\*\s*Day\s+\d+)', text, flags=re.IGNORECASE | re.MULTILINE)
        if len(fallback) > 1:
            for chunk in fallback[1:]:
                day_sections.append(("Day", chunk.strip()))
        else:
            day_sections = []

    if not (0 <= day_index < len(day_sections)):
        messages.error(request, f"Could not find tasks for {day_str}.")
        return redirect('view_study_plan', plan_id=plan.id)

    _, day_content = day_sections[day_index]

   
    task_lines = re.findall(r'(?m)^\s*(?:[-*]|\d+\.)\s*(.+)$', day_content)
    if not task_lines:
       
        task_lines = re.findall(r'(?m)^\s*(?:Task\s*\d+\s*[:\-])\s*(.+)$', day_content, flags=re.IGNORECASE)

    if not task_lines:
        messages.error(request, f"Could not find tasks for {day_str}.")
        return redirect('view_study_plan', plan_id=plan.id)

    try:
        base_date = plan.start_date or timezone.now().date()
    except Exception:
        base_date = timezone.now().date()
    target_date = base_date + timedelta(days=day_index)

    added_count = 0
    for raw in task_lines:
        clean = re.sub(r'<[^>]+>', '', raw).strip()  
        if not clean:
            continue

        title = f"{plan.subject} (Day {day_index + 1}): {clean}"

        
        Task.objects.create(
            user=user,
            title=title,
            status='INBOX',
            difficulty='Moderate',
            category='Other',
            memo='',                 # <<-- prevent NOT NULL IntegrityError
            study_plan=plan,
            scheduled_date=target_date
        )
        added_count += 1

    if added_count > 0:
        messages.success(request, f"Added {added_count} tasks from {day_str} to your main dashboard!")
        request.session['suppress_auto_activate'] = True
    else:
        messages.error(request, f"Could not find tasks for {day_str}.")

    return redirect('personal_dashboard')




@login_required
def delete_study_plan_view(request, plan_id):
    """Deletes a study plan."""
    plan = get_object_or_404(StudyPlan, id=plan_id, user=request.user)
    
    if request.method == 'POST':
        plan_name = plan.subject
        
        
        Task.objects.filter(study_plan=plan).delete() 
        
        plan.delete()
        messages.success(request, f"Plan '{plan_name}' has been deleted.")
    
    return redirect('plan_list')

@login_required
def complete_study_plan_view(request, plan_id):
    """Marks a study plan as completed."""
   
    plan = get_object_or_404(StudyPlan, id=plan_id, user=request.user)
    
    if request.method == 'POST':
        plan.is_completed = True
        plan.save()
        messages.success(request, f"Congratulations on completing the '{plan.subject}' plan!")
    
    return redirect('plan_list')



@login_required
def delete_completed_plans_view(request):
    if request.method == 'POST':
       
        plans = StudyPlan.objects.filter(user=request.user, is_completed=True)
        count = plans.count()
        
        if count > 0:
           
            Task.objects.filter(study_plan__in=plans).delete()
            plans.delete()
            messages.success(request, f"Successfully deleted {count} completed plan(s).")
        else:
            messages.info(request, "No completed plans to delete.")
            
    return redirect('plan_list')

@login_required
def profile_view(request):
    profile, created = Profile.objects.get_or_create(user=request.user)
    
    all_badges = Badge.objects.all()
    
    earned_badges = UserBadge.objects.filter(user=request.user).values_list('badge_id', flat=True)

    context = {
        'profile': profile,
        'all_badges': all_badges,
        'earned_badges': earned_badges,
        'xp_for_next_level': profile.level * 100
    }
    return render(request, 'core/profile.html', context)

@login_required
def add_team_task_view(request, team_id):
    team = get_object_or_404(Team, id=team_id)

    if request.method == 'POST' and request.user in team.members.all():
        title = request.POST.get('title')
        assignee_id = request.POST.get('assignee')

        if not title:
            messages.error(request, "Task title cannot be empty.")
            return redirect('team_dashboard', team_id=team.id)

        
        if assignee_id == 'all':
            for member in team.members.all():
                Task.objects.create(
                    user=request.user,         
                    team=team,
                    title=title,
                    assignee=member,
                    status='INBOX',
                    difficulty='Moderate',
                    category='Other',
                    memo='',                 
                )
            messages.success(request, f"Task '{title}' assigned to all team members.")
            return redirect('team_dashboard', team_id=team.id)

     
        assignee = None
        if assignee_id:
            try:
                assignee = team.members.get(id=assignee_id)
            except User.DoesNotExist:
                assignee = None

        Task.objects.create(
            user=request.user,
            team=team,
            title=title,
            assignee=assignee,
            status='INBOX',
            difficulty='Moderate',
            category='Other',
            memo='',  
        )

        if assignee:
            messages.success(request, f"Task '{title}' assigned to {assignee.username}.")
        else:
            messages.success(request, f"Task '{title}' added to team inbox.")

    return redirect('team_dashboard', team_id=team.id)


@login_required
def plan_list(request):
    """
    Simple view to render list of study plans for current user.
    Template: core/plan_list.html
    """
    user = request.user
    plans = StudyPlan.objects.filter(user=user).order_by('-created_at')
    context = {
        'plans': plans,
    }
    return render(request, 'core/plan_list.html', context)

