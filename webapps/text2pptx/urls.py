from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="pptx_page"),
    path("sample-extractor/", views.sample_extractor, name="pptx_sample_extractor"),
    path("extract_sample/", views.extract_sample_api, name="pptx_extract_sample_api"),
    path("extract_template/", views.extract_template, name="pptx_extract_template"),
    path("extract_template_batch/", views.extract_template_batch, name="pptx_extract_template_batch"),
    path("download-pptx/<str:filename>", views.download_pptx, name="pptx_download_pptx"),
    path("download-potx/<str:filename>", views.download_potx, name="pptx_download_potx"),
    path("generate_restored_pptx/", views.generate_restored_pptx, name="pptx_generate_restored_pptx"),
    path("template-admin/", views.template_admin, name="pptx_template_admin"),
    path("import-template/", views.import_template, name="pptx_import_template"),
    path("analyze-image-prompts/", views.analyze_image_prompts, name="pptx_analyze_image_prompts"),
    path("schema/extract/", views.schema_extract, name="pptx_schema_extract"),
    path("schema/analyze/", views.schema_analyze, name="pptx_schema_analyze"),
    path("generate/", views.generate_pptx, name="pptx_generate"),
]
