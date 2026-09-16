# api/__init__.py
from flask import Blueprint

api = Blueprint('api', __name__, url_prefix='/api')

from . import chatbot_view