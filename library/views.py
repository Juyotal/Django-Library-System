from rest_framework import viewsets, status
from rest_framework.response import Response
from .models import Author, Book, Member, Loan
from .serializers import AuthorSerializer, BookSerializer, MemberSerializer, LoanSerializer
from rest_framework.decorators import action
from django.utils import timezone
from django.db import models
from .tasks import send_loan_notification

class AuthorViewSet(viewsets.ModelViewSet):
    queryset = Author.objects.all()
    serializer_class = AuthorSerializer

class BookViewSet(viewsets.ModelViewSet):
    queryset = Book.objects.all()
    serializer_class = BookSerializer

    @action(detail=True, methods=['post'])
    def loan(self, request, pk=None):
        book = self.get_object()
        if book.available_copies < 1:
            return Response({'error': 'No available copies.'}, status=status.HTTP_400_BAD_REQUEST)
        member_id = request.data.get('member_id')
        try:
            member = Member.objects.get(id=member_id)
        except Member.DoesNotExist:
            return Response({'error': 'Member does not exist.'}, status=status.HTTP_400_BAD_REQUEST)
        loan = Loan.objects.create(book=book, member=member)
        book.available_copies -= 1
        book.save()
        send_loan_notification.delay(loan.id)
        return Response({'status': 'Book loaned successfully.'}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def return_book(self, request, pk=None):
        book = self.get_object()
        member_id = request.data.get('member_id')
        try:
            loan = Loan.objects.get(book=book, member__id=member_id, is_returned=False)
        except Loan.DoesNotExist:
            return Response({'error': 'Active loan does not exist.'}, status=status.HTTP_400_BAD_REQUEST)
        loan.is_returned = True
        loan.return_date = timezone.now().date()
        loan.save()
        book.available_copies += 1
        book.save()
        return Response({'status': 'Book returned successfully.'}, status=status.HTTP_200_OK)

class MemberViewSet(viewsets.ModelViewSet):
    queryset = Member.objects.all()
    serializer_class = MemberSerializer

    @action(detail=False, methods=['get'], url_path='top-active')
    def top_members(self, request):
        num_active_loans = models.Count('loans', filter=models.Q(loans__is_returned=False))
        top_active_members = Member.objects.annotate(
            num_active_loans=num_active_loans
        ).filter(num_active_loans__gt=0).order_by('-num_active_loans')[:5]

        result = []
        for member in top_active_members:
            result.append({
                'id': member.id,
                'username': member.user.username,
                'email': member.user.email,
                'active_loans': member.num_active_loans,
            })

        return Response({'status': 'Success.', 'data': result}, status=status.HTTP_200_OK)

class LoanViewSet(viewsets.ModelViewSet):
    queryset = Loan.objects.all()
    serializer_class = LoanSerializer

    @action(detail=True, methods=['post'])
    def extend_due_date(self, request, pk):
        loan = self.get_object()
        today = timezone.now().date()

        if loan.is_returned:
            return Response({'error': 'Can not Extend Returned Loan.'}, status=status.HTTP_400_BAD_REQUEST)

        if loan.due_date < today:
            return Response({'error': 'Can not Extend Overdue Loan.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            add_days = int(request.data.get("additional_days", ""))
        except ValueError:
            return Response({'error': 'Invalid additional_days Value.'}, status=status.HTTP_400_BAD_REQUEST)

        if add_days <= 0:
            return Response({'error': 'additional_days Should be a +ve integer'}, status=status.HTTP_400_BAD_REQUEST)

        loan.extend(add_days)
        serializer = self.get_serializer(loan)
        return Response(
            {'status': f'Successfully Extended Loan by {add_days}', 'data': serializer.data},
            status=status.HTTP_200_OK
        )