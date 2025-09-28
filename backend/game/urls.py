from django.urls import path
from .views import board_view, bingo_view

urlpatterns = [
    path('board', board_view, name='board'),      # GET /board
    path('bingo', bingo_view, name='bingo'),      # POST /bingo
]
