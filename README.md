# 🚀 Django + Daphne + Redis + Nginx Proxy Setup

This project runs a Django ASGI app with Redis and Nginx Proxy, all inside Docker.  
The reverse proxy automatically routes requests to Django using environment variables.

---

## 📦 Requirements

- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/)

---

## 🔧 Setup

### 1. Clone the repo
```bash
git clone https://github.com/saidjonrajapovv/yaxshilink.git
cd yourproject
````

### 2. Create required directories

These are used by `nginx-proxy`:

```bash
mkdir -p certs vhost.d html
```

### 3. Environment variables

Create a `.env` file in the project root with your Django configuration.

Example:

```
DJANGO_SECRET_KEY=your-secret-key
DEBUG=True
DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_EMAIL=admin@example.com
DJANGO_SUPERUSER_PASSWORD=admin123
```

---

## ▶️ Starting the Project

### 1. Clean build

```bash
docker-compose down -v
docker-compose up -d --build
```

This will:

* Build the Django app container
* Start Redis
* Start `nginx-proxy`
* Create a shared Docker network `webnet`

---

## ⚙️ Run Migrations and Create a Superuser

After containers are running, run the following commands **inside the Django container**:

```bash
# Enter the container shell
docker exec -it django-web bash

# Apply migrations
python manage.py makemigrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser
```

Alternatively, you can automate user creation via environment variables (see `.env` section above) using a startup script in your Dockerfile or entrypoint.

---

## 🌐 Accessing the App

* If running locally:

  * Visit → [http://localhost](http://localhost)

* If using a domain:

  * Set `VIRTUAL_HOST=yourdomain.com` in `docker-compose.yml`
  * Add that domain to Django’s `ALLOWED_HOSTS` in `settings.py`
  * Visit → `http://yourdomain.com`

* Django Admin:

  * Visit → [http://localhost/admin](http://localhost/admin)
  * Login with the superuser credentials you created.

---

## 🛠️ Useful Commands

Check running containers:

```bash
docker ps
```

View logs:

```bash
docker logs django-web
docker logs nginx-proxy
```

Restart and rebuild:

```bash
docker-compose down -v
docker-compose up -d --build
```

Run commands in the Django container:

```bash
docker exec -it django-web python manage.py shell
```

Inspect Docker network:

```bash
docker network inspect webnet
```

---

## 🐛 Troubleshooting

| Problem                            | Cause                         | Fix                                                  |
| ---------------------------------- | ----------------------------- | ---------------------------------------------------- |
| `502 Bad Gateway`                  | Django not reachable by proxy | Add `expose: "8000"` and restart                     |
| `network webnet not found`         | Network deleted               | Run `docker-compose down -v && docker-compose up -d` |
| Django `ALLOWED_HOSTS` error       | Missing domain/IP             | Update `ALLOWED_HOSTS` in `settings.py`              |
| Proxy doesn’t detect container     | Missing env vars              | Ensure `VIRTUAL_HOST` and `VIRTUAL_PORT` are set     |
| `django.db.utils.OperationalError` | DB not migrated               | Run `python manage.py migrate`                       |

---

## ✅ Summary

* `nginx-proxy` automatically detects Django when `VIRTUAL_HOST` and `VIRTUAL_PORT` are set.
* Both `nginx-proxy` and `django-web` must share the `webnet` network.
* Always run migrations before using Django.
* Create a superuser to access the admin panel.
* Verify that proxy logs show configuration generation.