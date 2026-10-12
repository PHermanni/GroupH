-- Azure SQL Database schema for Raspberry Pi IoT Monitor
CREATE TABLE dbo.Devices (
    DeviceId NVARCHAR(100) NOT NULL PRIMARY KEY,
    Name NVARCHAR(200) NOT NULL,
    Enabled BIT NOT NULL CONSTRAINT DF_Devices_Enabled DEFAULT (1),
    SamplingIntervalSeconds INT NOT NULL CONSTRAINT DF_Devices_SamplingInterval DEFAULT (60),
    RetentionDays INT NOT NULL CONSTRAINT DF_Devices_RetentionDays DEFAULT (90),
    LastSeenAt DATETIME2 NULL,
    CreatedAt DATETIME2 NOT NULL CONSTRAINT DF_Devices_CreatedAt DEFAULT (SYSUTCDATETIME()),
    CONSTRAINT CK_Devices_SamplingInterval CHECK (SamplingIntervalSeconds BETWEEN 5 AND 86400),
    CONSTRAINT CK_Devices_RetentionDays CHECK (RetentionDays BETWEEN 1 AND 3650)
);

CREATE TABLE dbo.Measurements (
    Id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    DeviceId NVARCHAR(100) NOT NULL,
    TemperatureC FLOAT NULL,
    HumidityPercent FLOAT NULL,
    MeasuredAt DATETIME2 NOT NULL,
    ReceivedAt DATETIME2 NOT NULL CONSTRAINT DF_Measurements_ReceivedAt DEFAULT (SYSUTCDATETIME()),
    Source NVARCHAR(20) NOT NULL CONSTRAINT DF_Measurements_Source DEFAULT ('sensor'),
    CONSTRAINT FK_Measurements_Devices FOREIGN KEY (DeviceId) REFERENCES dbo.Devices(DeviceId),
    CONSTRAINT CK_Measurements_Source CHECK (Source IN ('sensor', 'manual')),
    CONSTRAINT CK_Measurements_HasValue CHECK (TemperatureC IS NOT NULL OR HumidityPercent IS NOT NULL),
    CONSTRAINT CK_Measurements_Temperature CHECK (TemperatureC IS NULL OR TemperatureC BETWEEN -50 AND 100),
    CONSTRAINT CK_Measurements_Humidity CHECK (HumidityPercent IS NULL OR HumidityPercent BETWEEN 0 AND 100)
);

CREATE INDEX IX_Measurements_Device_MeasuredAt
ON dbo.Measurements (DeviceId, MeasuredAt DESC);

IF NOT EXISTS (SELECT 1 FROM dbo.Devices WHERE DeviceId = N'raspberrypi-01')
BEGIN
    INSERT INTO dbo.Devices (DeviceId, Name)
    VALUES (N'raspberrypi-01', N'Raspberry Pi 1');
END;
