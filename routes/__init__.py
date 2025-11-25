"""
Routes package - Flask Blueprint registration
"""

def register_routes(app):
    """Registriert alle Route-Blueprints bei der Flask-App."""
    from .main_routes import main_bp
    from .file_routes import file_bp
    from .analysis_routes import analysis_bp
    from .control_routes import control_bp
    from .admin_routes import admin_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(file_bp)
    app.register_blueprint(analysis_bp)
    app.register_blueprint(control_bp)
    app.register_blueprint(admin_bp)
