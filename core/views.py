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
from .models import Team, Todo
import re
import markdown as md
from django.core.mail import send_mail
from django.conf import settings
import random
from .models import OTPVerification
from django.contrib import messages
from better_profanity import profanity


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

# core/views.py
from django.db.models import Q
from .models import Todo, Profile, StudyPlan # Dono models ko import karein

# core/views.py
from django.db.models import Q
from .models import Todo, Profile, StudyPlan


@login_required
def personal_dashboard_view(request):
    user = request.user
    profile, created = Profile.objects.get_or_create(user=user)

    # Bina date waale team tasks
    assigned_tasks = Todo.objects.filter(assignee=user, scheduled_date__isnull=True, status='INBOX')
    
    # SARE TASKS (Personal + Team + Study Plan)
    # Exclude logic zaroori hai taaki 'assigned_tasks' aur 'active' yahan na dikhein
    all_my_tasks = Todo.objects.filter(
        Q(user=user) | Q(assignee=user)
    ).exclude(status='DELETED').distinct().order_by('scheduled_date', 'created')

    print(f"--- SMART PLANNER DEBUG ---")
    print(f"User: {user.username} | Total Todos in DB: {all_my_tasks.count()}")

    active_task = all_my_tasks.filter(status='ACTIVE').first()
    show_mood = True if not active_task else False
    
    # UP NEXT: Inbox waale wo tasks jo upar assigned section mein nahi hain
    pending_tasks = all_my_tasks.filter(status='INBOX').exclude(
        id__in=assigned_tasks.values_list('id', flat=True)
    )
    if active_task:
        pending_tasks = pending_tasks.exclude(id=active_task.id)
    
    context = {
        'active_task': active_task,
        'pending_tasks': pending_tasks, # Ab ye line se dikhenge
        'profile': profile,
        'assigned_tasks': assigned_tasks,
        'xp_for_next_level': profile.level * 100,
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
                priority=2,
                team=None,
                memo='' 
            )
            messages.success(request, f"AI Task '{new_task.title}' added to your inbox!")
            
            if not Task.objects.filter(user=user, status='ACTIVE', team=None).exists():
                new_task.status = 'ACTIVE' 
                new_task.save()

            if isinstance(sub_tasks_list, list):
                 sub_tasks_list = " ".join(sub_tasks_list)

           

            
    return redirect('personal_dashboard')


@login_required
def add_task_manual(request):
    if request.method == 'POST':
        user = request.user
        title = request.POST.get('title')
        priority_val = request.POST.get('priority', 2)
        
        # --- NAYI DATE VALUE LO ---
        scheduled_date = request.POST.get('scheduled_date')
        
        # Agar user date nahi dalta (waise humne required kiya hai), 
        # toh default aaj ki date rakho
        if not scheduled_date:
            scheduled_date = timezone.now().date()

        if title:
            Task.objects.create(
                user=user, 
                title=title, 
                status='INBOX', 
                priority=priority_val,
                scheduled_date=scheduled_date # Database mein save karo
            )
            
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
    
    # 1. Purane active task ko dhoondh kar INBOX mein waapas bhejo
    active_task = Task.objects.filter(
        Q(assignee=user) | Q(user=user, team=None),
        status='ACTIVE'
    ).first()
    
    if active_task:
        active_task.status = 'INBOX'
        active_task.save()

    # 2. Mood ke hisaab se naya task dhoondho (jo personal ho YA team ka ho)
    #    Snoozed tasks ko ignore karo
    #    Sabse pehle High Priority, fir sabse purana
    tasks_query = Task.objects.filter(
        Q(assignee=user) | Q(user=user, team=None),
        status='INBOX',
        difficulty=difficulty
    ).exclude(snoozed_until__gt=timezone.now()).order_by('-priority', 'created')

    suggested_task = tasks_query.first()

    # 3. Fallback logic: Agar uss difficulty ka task na mile, to koi bhi pending task le lo
    if not suggested_task:
        suggested_task = Task.objects.filter(
            Q(assignee=user) | Q(user=user, team=None),
            status='INBOX'
        ).exclude(snoozed_until__gt=timezone.now()).order_by('-priority', 'created').first()

    # 4. Naye task ko ACTIVE banao
    if suggested_task:
        suggested_task.status = 'ACTIVE'
        suggested_task.save()
        messages.success(request, f"New task activated: '{suggested_task.title}'")
    else:
        # Agar inbox khaali hai, to koi error nahi, bas message do
        messages.warning(request, "No pending tasks found to activate.")
        
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
    if request.method == 'POST':
        plan = get_object_or_404(StudyPlan, id=plan_id, user=request.user)
        user_selected_date = request.POST.get('manual_scheduled_date')
        
        if not user_selected_date:
            messages.error(request, "Please select a date first!")
            return redirect('view_study_plan', plan_id=plan.id)

        
        lines = plan.generated_plan.splitlines()
        found_day = False
        tasks_to_add = []

        # Day Number nikaalna (e.g., "Day 1" se "1" nikaalna)
        day_match = re.search(r'Day\s*(\d+)', day_str, re.IGNORECASE)
        day_num = day_match.group(1) if day_match else None

        for line in lines:
            line_strip = line.strip()
            if not line_strip: continue

            # 1. Day Section dhoondhein (Thoda flexible check)
            # Agar line mein "Day 1" ya "Day 01" hai
            if not found_day:
                if day_num and f"Day {day_num}" in line or day_str.lower() in line.lower():
                    found_day = True
                    continue
            
            # 2. Agar found_day True hai, toh lines collect karein
            if found_day:
                # Agar naya Day shuru ho jaye toh ruk jayein
                if re.match(r'^(#*\s*Day\s*\d+)', line_strip, re.IGNORECASE) and day_num not in line_strip:
                    break
                
                # Task lines: -, *, •, 1. ya bold tasks uthao
                # Bullets hata kar sirf text rakho
                clean_task = re.sub(r'^[\s\d\.\-\*\•\#]+', '', line_strip).strip()
                if clean_task and len(clean_task) > 3: # Chhoti lines skip karo
                    tasks_to_add.append(clean_task)

        # 3. SAVE LOGIC
        if not tasks_to_add:
            print(f"RESULT: No tasks found for {day_str} in the plan text.")
            messages.warning(request, f"Format Issue: No tasks found for '{day_str}'. Please check the AI Plan text.")
        else:
            for title in tasks_to_add:
                Todo.objects.create(
                    user=request.user,
                    title=title,
                    status='INBOX',
                    priority=2,
                    scheduled_date=user_selected_date
                )
            messages.success(request, f"Added {len(tasks_to_add)} tasks for {day_str} to your dashboard!")
            
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
        deadline = request.POST.get('deadline') # Aapne ye sahi liya hai

        if not title:
            messages.error(request, "Task title cannot be empty.")
            return redirect('team_dashboard', team_id=team.id)

        # Logic: Agar deadline empty string hai toh usey None (null) rakho
        task_deadline = deadline if deadline else None

        # Case 1: Agar task sabko assign karna ho
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
                    deadline=task_deadline # <-- Ye line add ki hai
                )
            messages.success(request, f"Task '{title}' assigned to all team members.")
            return redirect('team_dashboard', team_id=team.id)

        # Case 2: Agar kisi specific member ya inbox ko assign karna ho
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
            deadline=task_deadline 
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

def signup_view(request):
    if request.method == 'POST':
        # Use .get() to avoid MultiValueDictKeyError
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')

        if profanity.contains_profanity(username):
            messages.error(request, "Bhai, ye username allowed nahi hai. Kuch dhang ka rakho!")
            return redirect('signup')

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already taken.")
            return redirect('signup')
        
        # 1. User create karo par deactivate rakho (Secure way)
        user = User.objects.create_user(username=username, email=email, password=password)
        user.is_active = False 
        user.save()

        # 2. OTP generate aur DB mein save
        otp_code = str(random.randint(100000, 999999))
        OTPVerification.objects.create(user=user, otp=otp_code)

        # 3. Session mein sirf user ID rakho (No password!)
        request.session['verify_user_id'] = user.id

        # Send Email Logic
        try:
            send_mail("Verify Account", f"Your OTP: {otp_code}", settings.DEFAULT_FROM_EMAIL, [email])
            return redirect('verify_otp')
        except:
            user.delete() # Cleanup if mail fails
            messages.error(request, "Email failed.")
            return redirect('signup')

    return render(request, 'registration/signup.html')

def verify_otp_view(request):
    if request.method == 'POST':
        entered_otp = request.POST.get('otp')
        user_id = request.session.get('verify_user_id')
        
        if not user_id:
            return redirect('signup')

        try:
            user = User.objects.get(id=user_id)
            otp_obj = OTPVerification.objects.get(user=user, otp=entered_otp)
            
            # Success! Activate user
            user.is_active = True
            user.save()
            otp_obj.delete() # OTP use ho gaya toh delete kardo
            del request.session['verify_user_id']
            
            messages.success(request, "Verified! Login now.")
            return redirect('login')
        except:
            messages.error(request, "Invalid OTP.")
    
    return render(request, 'registration/verify_otp.html')


def signup_view(request):
    if request.method == 'POST':
        username = request.POST.get('username').strip()
        email = request.POST.get('email').strip().lower()
        password = request.POST.get('password')

        # 1. Profanity Check
        clean_username = re.sub(r'[^a-zA-Z]', '', username).lower()
        if profanity.contains_profanity(username) or profanity.contains_profanity(clean_username):
            messages.error(request, "Username contains prohibited words.")
            return redirect('signup')

        # 2. Existence Check
        if User.objects.filter(username__iexact=username).exists():
            messages.error(request, "Username already exists.")
            return redirect('signup')
        
        if User.objects.filter(email__iexact=email).exists():
            messages.error(request, "Email already registered.")
            return redirect('signup')

        # 3. Password Validation (Double check this during signup!)
        if len(password) < 8 or not re.search(r'[A-Z]', password) or \
           not re.search(r'[a-z]', password) or not re.search(r'[0-9]', password) or \
           not re.search(r'[@$!%*?&]', password):
            messages.error(request, "Password must be 8+ chars with Upper, Lower, Number, and Special char.")
            return redirect('signup')

        try:
            user = User.objects.create_user(username=username, email=email, password=password)
            user.is_active = False 
            user.save()

            otp_code = str(random.randint(100000, 999999))
            OTPVerification.objects.create(user=user, otp=otp_code)

            subject = "Verify your Smart Planner Account"
            message = f"Hello {username},\n\nYour code is: {otp_code}"
            
            # Send Mail
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [email])
            
            request.session['verify_user_id'] = user.id
            request.session['temp_email'] = email 
            return redirect('verify_otp')

        except Exception as e:
            print(f"MAIL ERROR: {e}") # CHECK YOUR TERMINAL FOR THIS
            if 'user' in locals():
                user.delete()
            messages.error(request, f"Mail delivery failed: {e}")
            return redirect('signup')

    return render(request, 'registration/signup.html')

@login_required
def assign_task_to_member_view(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        team_id = request.POST.get('team_id')
        assignee_id = request.POST.get('assignee_id')
        deadline = request.POST.get('deadline') # Jo naya field aapne add kiya
        
        team = get_object_or_404(Team, id=team_id, owner=request.user)
        assignee = get_object_or_404(User, id=assignee_id)

        # Todo table mein naya task create karna
        Todo.objects.create(
            user=request.user,       # Kisne banaya (Leader)
            title=title,
            team=team,               # Kis team ke liye hai
            assignee=assignee,       # Kisko kaam diya gaya hai
            deadline=deadline,       # Leader ki di hui deadline
            status='INBOX',          # Default status
            priority=3               # Team tasks high priority
        )
        
        messages.success(request, f"Task assigned to {assignee.username} successfully!")
        return redirect('team_dashboard') # Jahan aap team tasks dekhte hain
    
def schedule_assigned_task_view(request, task_id):
    # 1. Sirf wahi task uthao jahan current user 'assignee' hai
    task = get_object_or_404(Todo, id=task_id, assignee=request.user)
    
    if request.method == 'POST':
        user_date = request.POST.get('my_schedule_date')
        
        if user_date:
            # 2. Member ki chuni hui date ko 'scheduled_date' mein save karo
            task.scheduled_date = user_date
            task.save()
            
            messages.success(request, f"Task '{task.title}' scheduled for {user_date}!")
        else:
            messages.error(request, "Please select a date first.")
            
    return redirect('personal_dashboard')
