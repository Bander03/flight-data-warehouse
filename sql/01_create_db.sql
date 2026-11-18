-- 01_create_db.sql: drop and recreate the FlightDW database, then the stg and dw schemas.
-- SAFETY: this script only ever touches the database named exactly FlightDW.
-- Run:  sqlcmd -S localhost\SQLEXPRESS -E -b -i 01_create_db.sql
SET NOCOUNT ON;
USE master;
GO

IF DB_ID(N'FlightDW') IS NOT NULL
BEGIN
    ALTER DATABASE [FlightDW] SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
    DROP DATABASE [FlightDW];
END
GO

CREATE DATABASE [FlightDW];
GO
ALTER DATABASE [FlightDW] SET RECOVERY SIMPLE;   -- bulk loads of 569k rows: keep the log small
GO

USE FlightDW;
GO
CREATE SCHEMA stg;   -- staging: raw CSV text, one table per CSV
GO
CREATE SCHEMA dw;    -- the star schema
GO
PRINT 'FlightDW created with schemas stg and dw';
GO
