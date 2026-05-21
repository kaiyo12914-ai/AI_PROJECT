from rest_framework import serializers

from .models import DigitalTwinCategory, Document, DocumentChunk, IngestionJob, KnowledgeNode, QALog


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = "__all__"


class DocumentChunkSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentChunk
        exclude = ["embedding"]


class DigitalTwinCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = DigitalTwinCategory
        fields = "__all__"


class QALogSerializer(serializers.ModelSerializer):
    class Meta:
        model = QALog
        fields = "__all__"


class KnowledgeNodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = KnowledgeNode
        fields = "__all__"


class IngestionJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = IngestionJob
        fields = "__all__"
