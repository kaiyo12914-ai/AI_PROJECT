import re

with open('webapps/projectnotes/views.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the block inside `if request.method == "POST":` of `api_sources`
# from `if project_id <= 0 or not title or not upload:`
# down to `return _safe_json_response(...)`

start_marker = "        if project_id <= 0 or not title or not upload:\n            return _api_error(\"project_id, title, and file are required\")"
end_marker = "            }\n        )\n    \n    return _api_error(\"method not allowed\", status=405)"

if start_marker in content and end_marker in content:
    start_idx = content.find(start_marker)
    end_idx = content.find(end_marker) + len(end_marker)
    
    new_logic = """        if project_id <= 0 or not title or not upload:
            return _api_error("project_id, title, and file are required")
        
        file_content = upload.read()
        file_name = upload.name
        file_name_lower = file_name.lower()
        uploader_username = _current_user_id(request)
        
        from .tasks import start_source_upload_task
        job_id = start_source_upload_task(
            project_id=project_id,
            title=title,
            file_name=file_name,
            file_name_lower=file_name_lower,
            file_content=file_content,
            uploader_username=uploader_username
        )
        
        return _safe_json_response({"ok": True, "job_id": job_id})
    
    return _api_error("method not allowed", status=405)

@require_node("projectnotes", api=True)
def api_job_status(request, job_id: int):
    from .models import ProcessingJob
    try:
        job = ProcessingJob.objects.get(id=job_id)
        return _safe_json_response({
            "ok": True,
            "status": job.status,
            "progress_info": job.progress_info,
            "error_message": job.error_message,
            "target_id": job.target_id
        })
    except ProcessingJob.DoesNotExist:
        return _api_error("Job not found", status=404)"""
    
    content = content[:start_idx] + new_logic + content[end_idx:]
    
    with open('webapps/projectnotes/views.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Updated api_sources and added api_job_status")
else:
    print("Could not find markers")
