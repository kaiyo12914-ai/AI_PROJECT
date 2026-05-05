import os
import sys

sys.path.append(r'H:\AI\AI_TOOLS')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'webproj.settings')

import django
django.setup()

from webapps.database.db_factory import db_execute

sql = "DELETE FROM englishchat_question_bank WHERE question_id LIKE %s;"
db_execute('postgresql', sql, ['seed-%'])
print('Successfully deleted old seed questions.')
