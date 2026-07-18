from app import app

client = app.test_client()
routes = ['/dashboard','/resume','/job','/candidates','/analysis','/interview','/analytics','/reports','/settings']
for route in routes:
    response = client.get(route)
    print(route, response.status_code)
