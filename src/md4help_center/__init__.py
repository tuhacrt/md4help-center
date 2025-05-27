"""The md4help_center package can create md from Zendesk help center API."""

from md4help_center.info_generator import generate_info_file
from md4help_center.main import main

__all__ = ['generate_info_file', 'main']
