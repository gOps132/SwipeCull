from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('decisions/', views.decision_log, name='decision_log'),
    path('sessions/with-decisions/', views.sessions_with_decisions, name='sessions_with_decisions'),
    path('session/create/', views.create_session, name='create_session'),
    path('session/<int:session_id>/', views.session_detail, name='session_detail'),
    path('session/<int:session_id>/decide/', views.decide_file, name='decide_file'),
    path('session/<int:session_id>/undo/', views.undo_decision, name='undo_decision'),
    path('session/<int:session_id>/finalize/', views.finalize_session, name='finalize_session'),
]
