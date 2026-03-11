# core/tasks.py
from background_task import background
from django.core.mail import send_mail
from django.utils import timezone
from django.db.models import Q
from django.conf import settings
from django.contrib.auth.models import User
from .models import Todo, Profile

@background(schedule=60) # Ye task har 60 seconds baad queue check karega
def daily_reminder_job():
    print("Running Daily Reminder Job...")
    today = timezone.now().date()
    
    # 1. Wo saare users dhundho jinko aaj reminder NAHI mila hai
    profiles_to_check = Profile.objects.filter(
        Q(last_reminder_sent_date__lt=today) | Q(last_reminder_sent_date__isnull=True)
    )

    for profile in profiles_to_check:
        user = profile.user
        
        # 2. Check karo: Kya aaj koi 'Pending' task hai?
        pending_count = Todo.objects.filter(
            user=user, 
            status='INBOX', 
            scheduled_date=today
        ).count()

        if pending_count > 0:
            subject = f"🔔 Reminder: {pending_count} Tasks Waiting for You!"
            message = (
                f"Hi {user.username},\n\n"
                f"You have {pending_count} unfinished tasks scheduled for today on SmartPlanner.\n"
                f"Complete them now to maintain your productivity streak!\n\n"
                f"Go to Dashboard: http://127.0.0.1:8000/dashboard/\n\n"
                f"- Team SmartPlanner"
            )
            
            try:
                send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email])
                print(f" -> Sent mail to {user.email}")
                
                # 3. Update date taaki aaj dobara mail na jaye
                profile.last_reminder_sent_date = today
                profile.save()
                
            except Exception as e:
                print(f" -> Error sending to {user.email}: {e}")
        else:
            print(f" -> No pending tasks for {user.username}")