import os
import sys
import django

sys.path.insert(0, os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webproj.settings")
django.setup()

from webapps.vanna.models import TrainingDocumentation

# 刪除 nl2sql_oracle_schema 下的所有 TrainingDocumentation
deleted, _ = TrainingDocumentation.objects.filter(data_source__code="nl2sql_oracle_schema").delete()
print(f"Deleted {deleted} invalid documentation records from 'nl2sql_oracle_schema'.")
print("Remaining count:", TrainingDocumentation.objects.count())
