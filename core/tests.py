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
	def test_quiz_prompt_uses_extracted_concepts(self, mock_call_groq_api):
		mock_call_groq_api.return_value = json.dumps([
			{
				'question': 'Given a relation with partial dependency, which normalization step removes it?',
				'options': ['2NF', '1NF', 'BFS', 'UDP'],
				'answer': '2NF',
				'explanation': 'Partial dependency is removed in second normal form.',
			},
			{
				'question': 'A non-key attribute depends on another non-key attribute. Which normal form is affected?',
				'options': ['3NF', '1NF', 'Mutex', 'DNS'],
				'answer': '3NF',
				'explanation': 'This is a transitive dependency issue.',
			},
			{
				'question': 'A table keeps repeating the same values in multiple rows. What anomaly is most likely?',
				'options': ['Update anomaly', 'Deadlock', 'Handshake', 'Stack overflow'],
				'answer': 'Update anomaly',
				'explanation': 'Redundancy often leads to update anomalies.',
			},
			{
				'question': 'Which operation is best after identifying redundancy in a relation?',
				'options': ['Decompose the table', 'Add more duplicates', 'Change the quiz format', 'Ignore dependencies'],
				'answer': 'Decompose the table',
				'explanation': 'Decomposition removes redundant dependencies.',
			},
			{
				'question': 'When a composite key is present, what dependency should be checked first?',
				'options': ['Partial dependency', 'Packet loss', 'Semaphore wait', 'Heapify'],
				'answer': 'Partial dependency',
				'explanation': 'Composite keys can create partial dependencies.',
			},
		])

		from .ai_service import generate_task_quiz_with_ai

		questions = generate_task_quiz_with_ai(
			'Normalization in DBMS',
			'Prerequisites: SQL basics, database design. Step-by-step path: Apply 1NF, remove partial dependencies, remove transitive dependencies, validate decomposition.',
			'Moderate',
			5,
		)

		self.assertEqual(len(questions), 5)
		joined = ' '.join(question['question'].lower() for question in questions)
		self.assertIn('normal form', joined)
		self.assertIn('dependency', joined)
		self.assertFalse('what should' in joined)
		self.assertFalse('quiz' in joined)

		self.assertTrue(mock_call_groq_api.called)
		prompt = mock_call_groq_api.call_args.args[0]
		self.assertIn('Extracted concepts to use:', prompt)
		self.assertIn('Normalization in DBMS', prompt)
		self.assertIn('partial dependency', prompt.lower())
		self.assertIn('transitive dependency', prompt.lower())

	def test_quiz_generation_uses_dbms_domain_terms(self):
		from .ai_service import _extract_technical_concepts, _classify_quiz_domain

		concepts = _extract_technical_concepts(
			'Normalization in DBMS',
			'Prerequisites: SQL basics, database design, familiarity with data redundancy and dependency. Step-by-step path: 1NF, 2NF, 3NF, BCNF, partial dependencies, transitive dependencies.',
		)
		domain = _classify_quiz_domain('Normalization in DBMS', 'Prerequisites: SQL basics, database design, familiarity with data redundancy and dependency. Step-by-step path: 1NF, 2NF, 3NF, BCNF, partial dependencies, transitive dependencies.', concepts)

		self.assertEqual(domain, 'dbms')
		self.assertTrue(any('1NF' in concept or '2NF' in concept or '3NF' in concept for concept in concepts))
		self.assertTrue(any('dependency' in concept.lower() for concept in concepts))

	@patch('core.ai_service.call_groq_api')
	def test_quiz_regenerates_when_response_is_generic(self, mock_call_groq_api):
		mock_call_groq_api.side_effect = [
			json.dumps([
				{
					'question': 'What is the main idea of this topic?',
					'options': ['Understanding the topic', 'Random unrelated subject', 'Formatting issue', 'Time management'],
					'answer': 'Understanding the topic',
					'explanation': 'Generic answer.',
				},
			]),
			json.dumps([
				{
					'question': 'A relation contains repeating groups and non-atomic values. Which normal form is violated?',
					'options': ['1NF', '2NF', '3NF', 'BCNF'],
					'answer': '1NF',
					'explanation': 'Repeating groups violate first normal form.',
				},
				{
					'question': 'A non-key attribute depends on part of a composite key. What issue is this?',
					'options': ['Partial dependency', 'Transitive dependency', 'Deadlock', 'Starvation'],
					'answer': 'Partial dependency',
					'explanation': 'This is a partial dependency.',
				},
				{
					'question': 'When one non-key attribute determines another non-key attribute, which normal form is affected?',
					'options': ['3NF', '1NF', 'BFS', 'TCP'],
					'answer': '3NF',
					'explanation': 'This is a transitive dependency.',
				},
				{
					'question': 'What is the best correction when redundancy still remains after normalization?',
					'options': ['Decompose the relation further', 'Add filler columns', 'Change the question wording', 'Use a mutex'],
					'answer': 'Decompose the relation further',
					'explanation': 'Further decomposition can remove remaining redundancy.',
				},
				{
					'question': 'Which anomaly is likely when redundant data is updated in multiple rows?',
					'options': ['Update anomaly', 'Route mismatch', 'Stack overflow', 'Handshake failure'],
					'answer': 'Update anomaly',
					'explanation': 'Redundancy can cause update anomalies.',
				},
			]),
		]

		from .ai_service import generate_task_quiz_with_ai

		questions = generate_task_quiz_with_ai(
			'Normalization in DBMS',
			'Prerequisites: SQL basics, database design. Step-by-step path: Apply 1NF, remove partial dependencies, remove transitive dependencies, validate decomposition.',
			'Moderate',
			5,
		)

		self.assertEqual(len(questions), 5)
		self.assertGreaterEqual(mock_call_groq_api.call_count, 2)
		self.assertFalse(any('main idea' in question['question'].lower() for question in questions))
		self.assertFalse(any('random unrelated subject' in ' '.join(question['options']).lower() for question in questions))
