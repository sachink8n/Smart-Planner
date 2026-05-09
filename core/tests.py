from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
import json
from unittest.mock import patch

from .models import OTPVerification, StudyPlan, Todo, Profile


@override_settings(
	EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
	DEFAULT_FROM_EMAIL='noreply@example.com',
)
@patch.dict('os.environ', {'BREVO_API_KEY': ''}, clear=False)
class SignupFlowTests(TestCase):
	def test_signup_creates_inactive_user_and_redirects_to_verify(self):
		response = self.client.post(
			reverse('signup'),
			{
				'username': 'newuser',
				'email': 'newuser@example.com',
				'password': 'Password@123',
			},
		)

		self.assertRedirects(response, reverse('verify_otp'))
		user = User.objects.get(username='newuser')
		self.assertFalse(user.is_active)
		self.assertTrue(OTPVerification.objects.filter(user=user).exists())
		self.assertEqual(len(mail.outbox), 1)

	def test_signup_reuses_existing_inactive_user(self):
		user = User.objects.create_user(
			username='pendinguser',
			email='pending@example.com',
			password='OldPassword@123',
		)
		user.is_active = False
		user.save(update_fields=['is_active'])
		otp = OTPVerification.objects.create(user=user, otp='111111')
		original_created_at = otp.created_at
		old_password_hash = user.password

		response = self.client.post(
			reverse('signup'),
			{
				'username': 'pendinguser',
				'email': 'pending@example.com',
				'password': 'NewPassword@123',
			},
		)

		self.assertRedirects(response, reverse('verify_otp'))
		self.assertEqual(User.objects.filter(username='pendinguser').count(), 1)

		user.refresh_from_db()
		otp.refresh_from_db()
		self.assertTrue(user.check_password('NewPassword@123'))
		self.assertNotEqual(user.password, old_password_hash)
		self.assertNotEqual(otp.created_at, original_created_at)
		self.assertEqual(len(mail.outbox), 1)

	def test_verify_otp_activates_user_and_clears_pending_record(self):
		user = User.objects.create_user(
			username='verifyuser',
			email='verify@example.com',
			password='Password@123',
		)
		user.is_active = False
		user.save(update_fields=['is_active'])
		otp = OTPVerification.objects.create(user=user, otp='654321')

		session = self.client.session
		session['verify_user_id'] = user.id
		session['temp_email'] = user.email
		session.save()

		response = self.client.post(reverse('verify_otp'), {'otp': otp.otp})

		self.assertRedirects(response, reverse('login'))
		user.refresh_from_db()
		self.assertTrue(user.is_active)
		self.assertFalse(OTPVerification.objects.filter(user=user).exists())


class StudyPlanViewTests(TestCase):
	def test_view_study_plan_renders_when_day_title_has_slash(self):
		user = User.objects.create_user(
			username='planneruser',
			email='planner@example.com',
			password='Password@123',
		)
		self.client.login(username='planneruser', password='Password@123')

		plan = StudyPlan.objects.create(
			user=user,
			subject='Java',
			goal='Master exceptions',
			duration_days=3,
			generated_plan=(
				"## Day 1: Basics\n"
				"- Variables\n\n"
				"## Day 3: Java Exception Handling and Input/Output\n"
				"- Practice try/catch\n"
			),
		)

		response = self.client.get(reverse('view_study_plan', args=[plan.id]))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, '/add-day/Day%203/')


class TaskQuizFlowTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(
			username='quizuser',
			email='quiz@example.com',
			password='Password@123',
		)
		self.client.login(username='quizuser', password='Password@123')

	def test_complete_task_redirects_to_quiz(self):
		task = Todo.objects.create(
			user=self.user,
			title='Learn Django Views',
			status='INBOX',
			difficulty='Moderate',
			category='Learning',
			sub_tasks='- Prepare project\n- Read docs',
		)

		response = self.client.get(reverse('complete_task', args=[task.id]))

		self.assertRedirects(response, reverse('task_quiz', args=[task.id]))
		task.refresh_from_db()
		self.assertEqual(task.status, 'COMPLETED')
		self.assertTrue(task.quiz_pending)
		self.assertIsNotNone(task.quiz_completed_at)

	def test_submit_quiz_awards_points_and_marks_completed(self):
		task = Todo.objects.create(
			user=self.user,
			title='Learn Django Views',
			status='COMPLETED',
			difficulty='Hard',
			category='Learning',
			sub_tasks='- Prepare project\n- Read docs',
			quiz_pending=True,
			quiz_questions=[
				{
					'question': 'What is the first step?',
					'options': ['Read docs', 'Ignore it', 'Quit', 'Randomize'],
					'answer': 'Read docs',
					'explanation': 'Start by reading the docs.',
				},
				{
					'question': 'What should you prepare?',
					'options': ['Project setup', 'Nothing', 'Noise', 'Delay'],
					'answer': 'Project setup',
					'explanation': 'Prepare the project first.',
				},
				{
					'question': 'Which is a good habit?',
					'options': ['Practice', 'Skip', 'Procrastinate', 'Forget'],
					'answer': 'Practice',
					'explanation': 'Practice reinforces understanding.',
				},
				{
					'question': 'What is the goal?',
					'options': ['Learn', 'Avoid', 'Discard', 'Replace'],
					'answer': 'Learn',
					'explanation': 'The goal is to learn the topic.',
				},
				{
					'question': 'What follows the steps?',
					'options': ['Review', 'Sleep', 'Leave', 'Skip'],
					'answer': 'Review',
					'explanation': 'Reviewing reinforces learning.',
				},
			],
			quiz_completed_at=timezone.now(),
		)

		profile = Profile.objects.get(user=self.user)
		starting_xp = profile.xp

		response = self.client.post(
			reverse('submit_task_quiz', args=[task.id]),
			{
				'question_0': 'Read docs',
				'question_1': 'Project setup',
				'question_2': 'Practice',
				'question_3': 'Learn',
				'question_4': 'Review',
			},
		)

		self.assertEqual(response.status_code, 302)
		task.refresh_from_db()
		profile.refresh_from_db()
		self.assertTrue(task.quiz_submitted)
		self.assertTrue(task.quiz_awarded)
		self.assertEqual(task.quiz_score, 5)
		self.assertEqual(task.quiz_total_questions, 5)
		self.assertGreater(profile.xp, starting_xp)

	@patch('core.ai_service.call_groq_api')
	def test_add_magic_generates_prerequisites_heading(self, mock_call_groq_api):
		mock_call_groq_api.return_value = (
			"Prerequisites:\n"
			"- Python installed\n"
			"- Django project set up\n"
			"Step-by-step path:\n"
			"- Read the concept\n"
			"- Work through examples"
		)

		from .ai_service import get_sub_tasks_with_ai

		outline = get_sub_tasks_with_ai('Operating System Deadlock')

		self.assertIn('Prerequisites:', outline)
		self.assertIn('Step-by-step path:', outline)
		self.assertIn('- Python installed', outline)
		self.assertIn('- Work through examples', outline)

	@patch('core.ai_service.call_groq_api')
	def test_quiz_generation_rejects_generic_process_questions(self, mock_call_groq_api):
		mock_call_groq_api.return_value = json.dumps([
			{
				'question': 'What should you do first before starting?',
				'options': ['Review prerequisites', 'Submit it', 'Close the browser', 'Ignore the task'],
				'answer': 'Review prerequisites',
				'explanation': 'Generic workflow question.',
			},
			{
				'question': 'What is the most productive next step after preparation?',
				'options': ['Follow the step-by-step path', 'Stop working', 'Ignore the plan', 'Repeat the title'],
				'answer': 'Follow the step-by-step path',
				'explanation': 'Generic workflow question.',
			},
			{
				'question': 'Which summary best describes the task context?',
				'options': ['It is about the same task and its key steps', 'It is about a random unrelated topic', 'It has no relation to the task', 'It only checks spelling'],
				'answer': 'It is about the same task and its key steps',
				'explanation': 'Generic workflow question.',
			},
			{
				'question': 'What should you do first before starting?',
				'options': ['Review prerequisites', 'Submit it', 'Close the browser', 'Ignore the task'],
				'answer': 'Review prerequisites',
				'explanation': 'Generic workflow question.',
			},
			{
				'question': 'Which approach best matches the recommended difficulty for this task (Hard)?',
				'options': ['Use a structured, focused approach', 'Rush without planning', 'Skip all prerequisites', 'Do it randomly'],
				'answer': 'Use a structured, focused approach',
				'explanation': 'Generic workflow question.',
			},
		])

		from .ai_service import generate_task_quiz_with_ai

		questions = generate_task_quiz_with_ai('Operating System Deadlock', 'Focus on deadlock conditions and prevention.', 'Hard', 5)

		self.assertEqual(len(questions), 5)
		self.assertTrue(all('deadlock' in question['question'].lower() or 'operating system' in question['question'].lower() for question in questions))
		self.assertFalse(any('before starting' in question['question'].lower() for question in questions))
