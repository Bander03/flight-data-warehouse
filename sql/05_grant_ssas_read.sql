-- 05_grant_ssas_read.sql: lets the Analysis Services instance DEV read FlightDW (read-only).
-- Run it after EVERY rebuild of FlightDW (01_create_db.sql drops the database and with it this database
-- user, so the next Process Full of the cube fails with a login error), against the Express instance:
--   sqlcmd -S localhost\SQLEXPRESS -E -b -i sql\05_grant_ssas_read.sql
-- It is idempotent: running it again on an intact database changes nothing.
-- It creates a Windows login for the service account NT Service\MSOLAP$DEV and gives it
-- db_datareader on FlightDW only: no write rights, no other database. To undo it:
--   USE FlightDW; DROP USER [NT Service\MSOLAP$DEV];  USE master; DROP LOGIN [NT Service\MSOLAP$DEV];
SET NOCOUNT ON;
USE master;
GO
IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'NT Service\MSOLAP$DEV')
    CREATE LOGIN [NT Service\MSOLAP$DEV] FROM WINDOWS;
GO
USE FlightDW;
GO
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'NT Service\MSOLAP$DEV')
    CREATE USER [NT Service\MSOLAP$DEV] FOR LOGIN [NT Service\MSOLAP$DEV];
GO
ALTER ROLE db_datareader ADD MEMBER [NT Service\MSOLAP$DEV];
GO
PRINT 'NT Service\MSOLAP$DEV can now read FlightDW (db_datareader).';
GO
