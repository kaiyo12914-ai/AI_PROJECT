with open('webapps/projectnotes/urls.py', 'r', encoding='utf-8') as f:
    content = f.read()

if 'api_job_status' not in content:
    content = content.replace(
        'path("overview/", views.api_overview, name="overview"),',
        'path("overview/", views.api_overview, name="overview"),\n    path("jobs/<int:job_id>/", views.api_job_status, name="job_status"),'
    )
    with open('webapps/projectnotes/urls.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Added api_job_status to urls.py")
