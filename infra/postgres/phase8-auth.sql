\getenv auth_user AUTH_DB_USER
\getenv auth_password AUTH_DB_PASSWORD

SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'auth_user', :'auth_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'auth_user')
\gexec

SELECT format('CREATE DATABASE %I OWNER %I', 'auth', :'auth_user')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'auth')
\gexec

REVOKE ALL ON DATABASE auth FROM PUBLIC;
GRANT CONNECT ON DATABASE auth TO :"auth_user";
