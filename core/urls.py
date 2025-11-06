from django.urls import path
from . import views

urlpatterns = [
   
    path('', views.personal_dashboard_view, name='personal_dashboard'),


    path('createtodo_ai/', views.createtodo_ai, name='createtodo_ai'),
    path('add_manual/', views.add_task_manual, name='add_task_manual'),

    path('complete/<int:task_id>/', views.complete_task, name='complete_task'),
    path('delete/<int:task_id>/', views.delete_task, name='delete_task'),
    path('snooze/<int:task_id>/', views.snooze_task, name='snooze_task'),

   
    path('task/start/<int:task_id>/', views.start_task_timer, name='start_task_timer'),
    path('task/add_time/<int:task_id>/', views.add_time_to_timer, name='add_time_to_timer'),
    

    path('history/', views.task_history_view, name='task_history'),
    path('history/reset/', views.reset_history_view, name='reset_history'),

    path('suggest/<str:difficulty>/', views.suggest_task_by_mood, name='suggest_task_by_mood'),
   
    path('relax-mode/', views.relax_mode_view, name='relax_mode'),

    path('teams/', views.team_list_view, name='team_list'),
    path('teams/create/', views.create_team_view, name='create_team'),

    path('teams/<int:team_id>/', views.team_dashboard_view, name='team_dashboard'),
    
    path('teams/<int:team_id>/add_task/', views.add_team_task_view, name='add_team_task'),

    path('teams/<int:team_id>/invite/', views.invite_member_view, name='invite_member'),

    path('generate-plan/', views.create_study_plan_view, name='generate_plan'),

    path('study-plan/create/', views.create_study_plan_view, name='create_study_plan'),
    path('study-plan/<int:plan_id>/', views.view_study_plan_view, name='view_study_plan'),
    path('study-plan/<int:plan_id>/add-day/<str:day_str>/', views.add_plan_day_tasks_view, name='add_plan_day_tasks'), 

    path('plans/', views.plan_list, name='plan_list'),

    path('study-plan/<int:plan_id>/delete/', views.delete_study_plan_view, name='delete_study_plan'),

    path('study-plan/<int:plan_id>/complete/', views.complete_study_plan_view, name='complete_study_plan'),

    path('profile/', views.profile_view, name='profile'),

    path('plans/delete-completed/', views.delete_completed_plans_view, name='delete_completed_plans'),

    


]


