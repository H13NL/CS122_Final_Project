from django.shortcuts import render
from django.http import HttpResponse


def home(request):
    return HttpResponse("YouTube Comment Sentiment Analysis")
# Create your views here.
