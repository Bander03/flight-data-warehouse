-- 02_stg_tables.sql: staging tables that mirror the CSV files (column names keep the source spelling,
-- including 'ariport'). Everything is NVARCHAR so BULK INSERT never fails on conversion;
-- typing and validation happen in 04_load.sql. Re-runnable: drops and recreates the stg tables.
SET NOCOUNT ON;
USE FlightDW;
GO

DROP TABLE IF EXISTS stg.fact_flight_segment;
DROP TABLE IF EXISTS stg.dim_ticket;
DROP TABLE IF EXISTS stg.dim_passenger;
DROP TABLE IF EXISTS stg.dim_airport;
DROP TABLE IF EXISTS stg.dim_airline;
DROP TABLE IF EXISTS stg.dim_plane;
DROP TABLE IF EXISTS stg.dim_seat;
DROP TABLE IF EXISTS stg.dim_price_range;
DROP TABLE IF EXISTS stg.dim_date;
GO

CREATE TABLE stg.fact_flight_segment (
    PriceRangeID        NVARCHAR(50), Departure_ariportID NVARCHAR(50), Transit_ariportID NVARCHAR(50),
    Landing_ariportID   NVARCHAR(50), DepartureDateID     NVARCHAR(50), ArrivalDateID     NVARCHAR(50),
    PassengerID         NVARCHAR(50), TicketID            NVARCHAR(50), PlaneID           NVARCHAR(50),
    CabinID             NVARCHAR(50), mileage             NVARCHAR(50), Price             NVARCHAR(50),
    Rate                NVARCHAR(50), ian                 NVARCHAR(50)
);
CREATE TABLE stg.dim_ticket (
    TicketID NVARCHAR(50), departureTime NVARCHAR(50), delayTime NVARCHAR(50),
    arrivalTime NVARCHAR(50), FlightNo NVARCHAR(50), IsSupplemented NVARCHAR(50)
);
CREATE TABLE stg.dim_passenger (
    PassengerID NVARCHAR(50), PassengerGender NVARCHAR(50), PassengerAge NVARCHAR(50),
    PassengerWorkplace NVARCHAR(400), FFP_TIER NVARCHAR(50), FLIGHT_COUNT NVARCHAR(50),
    PassengerName NVARCHAR(200)
);
CREATE TABLE stg.dim_airport (
    AirportID NVARCHAR(50), ariport NVARCHAR(200), airportCode NVARCHAR(50),
    Ariport_X NVARCHAR(50), Ariport_y NVARCHAR(50), city NVARCHAR(200)
);
CREATE TABLE stg.dim_airline (
    AirlinesID NVARCHAR(50), airlines NVARCHAR(200), airlinesCode NVARCHAR(50), planeNumber NVARCHAR(50)
);
CREATE TABLE stg.dim_plane (
    PlaneID NVARCHAR(50), planeModel NVARCHAR(200), SeatNum NVARCHAR(50)
);
CREATE TABLE stg.dim_seat (
    CabinID NVARCHAR(50), CabinClass NVARCHAR(50), SeatRow NVARCHAR(50), SeatLine NVARCHAR(50)
);
CREATE TABLE stg.dim_price_range (
    PriceRangeID NVARCHAR(50), MinNum NVARCHAR(50), MaxNum NVARCHAR(50), PriceGrade NVARCHAR(50)
);
CREATE TABLE stg.dim_date (
    DateRangeID NVARCHAR(50), [Date] NVARCHAR(50), [Year] NVARCHAR(50), [Month] NVARCHAR(50)
);
GO
PRINT 'stg tables created';
GO
