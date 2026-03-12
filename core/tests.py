from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from unittest.mock import patch

from .models import OTPVerification, StudyPlan


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
