\getenv catalog_user CATALOG_DB_USER
\getenv catalog_password CATALOG_DB_PASSWORD
\getenv orders_user ORDERS_DB_USER
\getenv orders_password ORDERS_DB_PASSWORD
\getenv payments_user PAYMENTS_DB_USER
\getenv payments_password PAYMENTS_DB_PASSWORD
\getenv inventory_user INVENTORY_DB_USER
\getenv inventory_password INVENTORY_DB_PASSWORD
\getenv notifications_user NOTIFICATIONS_DB_USER
\getenv notifications_password NOTIFICATIONS_DB_PASSWORD
\getenv auth_user AUTH_DB_USER
\getenv auth_password AUTH_DB_PASSWORD

CREATE ROLE :"catalog_user" LOGIN PASSWORD :'catalog_password';
CREATE ROLE :"orders_user" LOGIN PASSWORD :'orders_password';
CREATE ROLE :"payments_user" LOGIN PASSWORD :'payments_password';
CREATE ROLE :"inventory_user" LOGIN PASSWORD :'inventory_password';
CREATE ROLE :"notifications_user" LOGIN PASSWORD :'notifications_password';
CREATE ROLE :"auth_user" LOGIN PASSWORD :'auth_password';

CREATE DATABASE catalog OWNER :"catalog_user";
CREATE DATABASE orders OWNER :"orders_user";
CREATE DATABASE payments OWNER :"payments_user";
CREATE DATABASE inventory OWNER :"inventory_user";
CREATE DATABASE notifications OWNER :"notifications_user";
CREATE DATABASE auth OWNER :"auth_user";

REVOKE ALL ON DATABASE catalog FROM PUBLIC;
REVOKE ALL ON DATABASE orders FROM PUBLIC;
REVOKE ALL ON DATABASE payments FROM PUBLIC;
REVOKE ALL ON DATABASE inventory FROM PUBLIC;
REVOKE ALL ON DATABASE notifications FROM PUBLIC;
REVOKE ALL ON DATABASE auth FROM PUBLIC;
GRANT CONNECT ON DATABASE catalog TO :"catalog_user";
GRANT CONNECT ON DATABASE orders TO :"orders_user";
GRANT CONNECT ON DATABASE payments TO :"payments_user";
GRANT CONNECT ON DATABASE inventory TO :"inventory_user";
GRANT CONNECT ON DATABASE notifications TO :"notifications_user";
GRANT CONNECT ON DATABASE auth TO :"auth_user";
