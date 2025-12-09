from celery import shared_task
from .models import Loan
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone


@shared_task
def send_loan_notification(loan_id):
    try:
        loan = Loan.objects.get(id=loan_id)
        member_email = loan.member.user.email
        book_title = loan.book.title
        send_mail(
            subject='Book Loaned Successfully',
            message=f'Hello {loan.member.user.username},\n\nYou have successfully loaned "{book_title}".\nPlease return it by the due date.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[member_email],
            fail_silently=False,
        )
    except Loan.DoesNotExist:
        pass


@shared_task
def check_overdue_loans():
    today = timezone.now().date()
    overdue_loans = Loan.objects.filter(
        is_returned=False,
        due_date__lt=today,
    ).select_related('member__user', 'book')

    if not overdue_loans.exists():
        return f'No Overdue Loan as of {today}'

    emails_sent = 0
    for loan in overdue_loans:
        try:
            member_email = loan.member.user.email
            member_user = loan.member.user.username
            book_title = loan.book.title
            overdue_days = (today - loan.due_date).days
            message = f"Hello {member_user} the Book {book_title} is overdue {overdue_days} Days. Please Return It ASAP."
            send_mail(
                subject='OverDue Loan!!!',
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[member_email],
                fail_silently=False,
            )
            emails_sent += 1
        except Exception as e:
            print(f"failed to Send email to {member_email}: {e}")
            continue

    return f'Sent {emails_sent} emails for {len(overdue_loans)} Loans.'


