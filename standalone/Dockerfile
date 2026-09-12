FROM python:3.9-slim
WORKDIR /app
RUN pip install --no-cache-dir Flask==1.1.2 Werkzeug==1.0.1 Jinja2==2.11.3 itsdangerous==1.1.0 click==7.1.2 MarkupSafe==1.1.1 PyMySQL gunicorn
COPY server server
COPY standalone standalone
EXPOSE 8091
CMD ["gunicorn", "--bind", "0.0.0.0:8091", "--workers", "2", "standalone.wsgi:application"]
