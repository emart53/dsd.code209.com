import os
import sys

sys.path.insert(0, '/home/codeeqid/dsd.code209.com')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pricebook_manager.settings')

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
