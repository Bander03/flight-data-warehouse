-- 03_dw_tables.sql: the star schema. Drops and recreates the dw tables.
-- Surrogate keys equal the source IDs, so the fact load is a straight type conversion.
SET NOCOUNT ON;
SET QUOTED_IDENTIFIER ON;
USE FlightDW;
GO

DROP TABLE IF EXISTS dw.Fact_FlightSegment;
DROP TABLE IF EXISTS dw.DimTicket;
DROP TABLE IF EXISTS dw.DimAirline;
DROP TABLE IF EXISTS dw.DimDate;
DROP TABLE IF EXISTS dw.DimPassenger;
DROP TABLE IF EXISTS dw.DimAirport;
DROP TABLE IF EXISTS dw.DimPlane;
DROP TABLE IF EXISTS dw.DimSeat;
DROP TABLE IF EXISTS dw.DimPriceRange;
GO

CREATE TABLE dw.DimDate (
    DateKey          INT          NOT NULL CONSTRAINT PK_DimDate PRIMARY KEY,
    FullDate         DATE         NOT NULL CONSTRAINT UQ_DimDate_FullDate UNIQUE,
    [Year]           SMALLINT     NOT NULL,
    [Quarter]        TINYINT      NOT NULL,
    [Month]          TINYINT      NOT NULL,
    [Day]            TINYINT      NOT NULL,
    [DayOfWeek]      TINYINT      NOT NULL,            -- 1 = Monday ... 7 = Sunday
    MonthName        NVARCHAR(10) NOT NULL,            -- English: January ... December
    YearMonth        CHAR(7)      NOT NULL,            -- e.g. '2021-02' (sorts naturally)
    QuarterName      NVARCHAR(8)  NOT NULL,            -- e.g. '2021 Q1'
    DayName          NVARCHAR(10) NOT NULL,            -- English: Monday ... Sunday
    IsSpringFestival BIT          NOT NULL             -- 1 for 2021-02-11 .. 2021-02-17
);

CREATE TABLE dw.DimPassenger (
    PassengerKey  INT           NOT NULL CONSTRAINT PK_DimPassenger PRIMARY KEY,
    Gender        NVARCHAR(10)  NULL,
    Age           SMALLINT      NULL,
    AgeBand       NVARCHAR(10)  NOT NULL,              -- <25, 25-34, 35-44, 45-54, 55-64, 65+, Unknown
    AgeBandOrder  TINYINT       NOT NULL,              -- 1 (<25) ... 6 (65+), 7 = Unknown: sort key for AgeBand
    Workplace     NVARCHAR(400) NULL,
    FFPTier       TINYINT       NOT NULL,
    FlightCount   INT           NOT NULL,
    PassengerName NVARCHAR(200) NULL
);

CREATE TABLE dw.DimAirline (
    AirlineKey   INT           NOT NULL CONSTRAINT PK_DimAirline PRIMARY KEY,
    AirlineName  NVARCHAR(200) NOT NULL,
    AirlineCode  NVARCHAR(10)  NOT NULL CONSTRAINT UQ_DimAirline_Code UNIQUE,
    PlaneNumber  INT           NULL
);

CREATE TABLE dw.DimTicket (
    TicketKey      INT           NOT NULL CONSTRAINT PK_DimTicket PRIMARY KEY,
    FlightNo       NVARCHAR(20)  NOT NULL,
    DepartureTime  DATETIME2(0)  NOT NULL,
    DelayMinutes   INT           NOT NULL,
    ArrivalTime    DATETIME2(0)  NOT NULL,
    AirlineKey     INT           NOT NULL,             -- from the two-letter FlightNo prefix
    IsSupplemented BIT           NOT NULL,
    CONSTRAINT FK_DimTicket_Airline FOREIGN KEY (AirlineKey) REFERENCES dw.DimAirline (AirlineKey)
);

CREATE TABLE dw.DimAirport (
    AirportKey   INT           NOT NULL CONSTRAINT PK_DimAirport PRIMARY KEY,   -- 0 = 'No stopover'
    AirportName  NVARCHAR(200) NOT NULL,
    AirportCode  NVARCHAR(10)  NULL,                   -- blank in the source for 47 of 184 airports
    Province     NVARCHAR(200) NULL,
    Longitude    DECIMAL(12,8) NULL,
    Latitude     DECIMAL(12,8) NULL
);

CREATE TABLE dw.DimPlane (
    PlaneKey   INT           NOT NULL CONSTRAINT PK_DimPlane PRIMARY KEY,
    PlaneModel NVARCHAR(200) NOT NULL,
    SeatCount  INT           NOT NULL,
    SizeClass  NVARCHAR(10)  NOT NULL                  -- from SeatCount, not the source's size label:
                                                       -- Wide >= 250 seats, Narrow 100-249, Small < 100
);

CREATE TABLE dw.DimSeat (
    CabinKey   INT          NOT NULL CONSTRAINT PK_DimSeat PRIMARY KEY,
    CabinClass NCHAR(1)     NOT NULL,                  -- F / C / Y
    SeatRow    SMALLINT     NOT NULL,
    SeatLine   NVARCHAR(5)  NOT NULL
);

CREATE TABLE dw.DimPriceRange (
    PriceRangeKey INT NOT NULL CONSTRAINT PK_DimPriceRange PRIMARY KEY,
    MinPrice      INT NOT NULL,
    MaxPrice      INT NOT NULL,
    PriceGrade    INT NOT NULL
);

CREATE TABLE dw.Fact_FlightSegment (
    SegmentID           INT           NOT NULL CONSTRAINT PK_Fact_FlightSegment PRIMARY KEY,   -- source 'ian'
    DepartureDateKey    INT           NOT NULL,
    ArrivalDateKey      INT           NOT NULL,
    PassengerKey        INT           NOT NULL,
    TicketKey           INT           NOT NULL,
    DepartureAirportKey INT           NOT NULL,
    TransitAirportKey   INT           NOT NULL,        -- 0 = no stopover
    LandingAirportKey   INT           NOT NULL,
    PlaneKey            INT           NOT NULL,
    CabinKey            INT           NOT NULL,
    PriceRangeKey       INT           NOT NULL,
    Price               INT           NOT NULL,
    Rate                DECIMAL(4,2)  NOT NULL,
    Mileage             INT           NOT NULL,
    HasStopover         TINYINT       NOT NULL CONSTRAINT CK_Fact_HasStopover CHECK (HasStopover IN (0, 1)),
    SegmentCount        TINYINT       NOT NULL CONSTRAINT DF_Fact_SegmentCount DEFAULT (1)
                                                CONSTRAINT CK_Fact_SegmentCount CHECK (SegmentCount = 1),
    CONSTRAINT FK_Fact_DepartureDate    FOREIGN KEY (DepartureDateKey)    REFERENCES dw.DimDate (DateKey),
    CONSTRAINT FK_Fact_ArrivalDate      FOREIGN KEY (ArrivalDateKey)      REFERENCES dw.DimDate (DateKey),
    CONSTRAINT FK_Fact_Passenger        FOREIGN KEY (PassengerKey)        REFERENCES dw.DimPassenger (PassengerKey),
    CONSTRAINT FK_Fact_Ticket           FOREIGN KEY (TicketKey)           REFERENCES dw.DimTicket (TicketKey),
    CONSTRAINT FK_Fact_DepartureAirport FOREIGN KEY (DepartureAirportKey) REFERENCES dw.DimAirport (AirportKey),
    CONSTRAINT FK_Fact_TransitAirport   FOREIGN KEY (TransitAirportKey)   REFERENCES dw.DimAirport (AirportKey),
    CONSTRAINT FK_Fact_LandingAirport   FOREIGN KEY (LandingAirportKey)   REFERENCES dw.DimAirport (AirportKey),
    CONSTRAINT FK_Fact_Plane            FOREIGN KEY (PlaneKey)            REFERENCES dw.DimPlane (PlaneKey),
    CONSTRAINT FK_Fact_Cabin            FOREIGN KEY (CabinKey)            REFERENCES dw.DimSeat (CabinKey),
    CONSTRAINT FK_Fact_PriceRange       FOREIGN KEY (PriceRangeKey)       REFERENCES dw.DimPriceRange (PriceRangeKey)
);
GO
CREATE INDEX IX_DimTicket_AirlineKey ON dw.DimTicket (AirlineKey);
CREATE INDEX IX_Fact_TicketKey       ON dw.Fact_FlightSegment (TicketKey);
GO
PRINT 'dw tables created';
GO
