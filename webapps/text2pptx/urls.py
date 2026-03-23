from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="pptx_page"),
    path("template-admin/", views.template_admin, name="pptx_template_admin"),
    path("import-template/", views.import_template, name="pptx_import_template"),
    path("analyze-image-prompts/", views.analyze_image_prompts, name="pptx_analyze_image_prompts"),
    path("generate/", views.generate_pptx, name="pptx_generate"),
]
