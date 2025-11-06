# core/models.py
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver
from datetime import timedelta



class Team(models.Model):
    name = models.CharField(max_length=100)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="owned_teams")
    members = models.ManyToManyField(User, related_name="teams")

    def __str__(self):
        return self.name


class StudyPlan(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='study_plans')
    subject = models.CharField(max_length=200)
    goal = models.TextField()
    duration_days = models.IntegerField(default=7)
    generated_plan = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_completed = models.BooleanField(default=False)

   
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.subject} Plan for {self.user.username}"

    def save(self, *args, **kwargs):
        if not self.end_date:
            self.end_date = self.start_date + timedelta(days=self.duration_days - 1)
        if self.is_active:
            StudyPlan.objects.filter(user=self.user, is_active=True).exclude(id=self.id).update(is_active=False)
        super().save(*args, **kwargs)



class Todo(models.Model):
    DIFFICULTY_CHOICES = [
        ('Easy', 'Easy'),
        ('Moderate', 'Moderate'),
        ('Hard', 'Hard'),
    ]
    STATUS_CHOICES = [
        ('INBOX', 'Inbox'),
        ('ACTIVE', 'Active'),
        ('COMPLETED', 'Completed'),
        ('DELETED', 'Deleted'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_tasks')
    title = models.CharField(max_length=200)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='INBOX')
    created = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)
    snoozed_until = models.DateTimeField(null=True, blank=True)

    category = models.CharField(max_length=50, default='Other')
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_CHOICES, default='Moderate')
    time_estimate_minutes = models.IntegerField(default=25, null=True, blank=True)
    sub_tasks = models.JSONField(null=True, blank=True)
    datecompleted = models.DateTimeField(null=True, blank=True)
    memo = models.TextField(default='', blank=True)
    important = models.BooleanField(default=False)

    team = models.ForeignKey(Team, on_delete=models.CASCADE, null=True, blank=True, related_name='team_tasks')
    assignee = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_tasks")

    timer_start_time = models.DateTimeField(null=True, blank=True)
    timer_seconds_remaining = models.IntegerField(null=True, blank=True)

 
    study_plan = models.ForeignKey('StudyPlan', on_delete=models.SET_NULL, null=True, blank=True, related_name='tasks')
    scheduled_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return self.title



class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    xp = models.IntegerField(default=0)
    level = models.IntegerField(default=1)

    MOOD_CHOICES = [
        ('HAPPY', 'Happy'),
        ('OKAY', 'Okay'),
        ('STRESSED', 'Stressed'),
    ]
    mood = models.CharField(max_length=10, choices=MOOD_CHOICES, default='OKAY')

    last_early_bird_date = models.DateField(null=True, blank=True)
    early_bird_streak = models.IntegerField(default=0)
    last_night_owl_date = models.DateField(null=True, blank=True)
    night_owl_streak = models.IntegerField(default=0)

    def get_title(self):
        titles = [
            (30, "Procrastination's Bane"), (20, "Momentum Master"),
            (15, "Productivity Knight"), (10, "Task Slayer"),
            (5, "The Finisher"), (1, "The Initiator"),
        ]
        title = "Beginner"
        for level, title_name in titles:
            if self.level >= level:
                title = title_name
                break
        return title

    def __str__(self):
        return self.user.username


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)



class Badge(models.Model):
    badge_id = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField()
    icon = models.CharField(max_length=10, default="🏆")

    def __str__(self):
        return self.name


class UserBadge(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='badges')
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE)
    earned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'badge')
