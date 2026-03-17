from webapps.portal.models import PortalUsageLog
from django.utils import timezone
PortalUsageLog.objects.create(
    used_date=timezone.localdate(),
    program_code="TEST",
    user_id="U1",
    user_name="N1",
    path="/test/",
    method="GET",
    ip="127.0.0.1",
)
PortalUsageLog.objects.count()
