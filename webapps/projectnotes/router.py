class ProjectNotesRouter:
    """
    A router to control all database operations on models in the
    projectnotes application, routing them to PostgreSQL.
    """
    route_app_labels = {'projectnotes'}
    db_name = 'projectnotes_db'

    def db_for_read(self, model, **hints):
        if model._meta.app_label in self.route_app_labels:
            return self.db_name
        return None

    def db_for_write(self, model, **hints):
        if model._meta.app_label in self.route_app_labels:
            return self.db_name
        return None

    def allow_relation(self, obj1, obj2, **hints):
        # Allow relations if a model in the projectnotes app is involved.
        if (
            obj1._meta.app_label in self.route_app_labels or
            obj2._meta.app_label in self.route_app_labels
        ):
           return True
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label in self.route_app_labels:
            return db == self.db_name
        # other apps shouldn't migrate to projectnotes_db
        if db == self.db_name:
            return False
        return None
