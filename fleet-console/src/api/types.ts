// Names for the generated OpenAPI types the console uses (ADR 0013: never hand-written).
import type { components } from './generated/schema';

type Schemas = components['schemas'];

export type AircraftLive = Schemas['AircraftLive'];
export type TelemetryView = Schemas['TelemetryView'];
export type SwarmView = Schemas['SwarmView'];
export type LeaseView = Schemas['LeaseView'];
export type UserRef = Schemas['UserRef'];
export type CommandView = Schemas['CommandView'];
export type CommandTargetView = Schemas['CommandTargetView'];
export type CommandKind = Schemas['CommandKind'];
export type AlertView = Schemas['AlertView'];
export type GroupOut = Schemas['GroupOut'];
export type GroupPage = Schemas['GroupPage'];
export type ConfirmationProblem = Schemas['ConfirmationProblem'];
export type ConfirmationSummary = Schemas['ConfirmationSummary'];
export type LoginResponse = Schemas['LoginResponse'];
export type MeResponse = Schemas['MeResponse'];
export type Permission = Schemas['Permission'];
export type Role = Schemas['Role'];
export type LinkState = Schemas['LinkState'];
export type Airframe = Schemas['Airframe'];
export type FlightMode = Schemas['FlightMode'];
export type GeoPoint = Schemas['GeoPoint'];
export type Problem = Schemas['Problem'];
export type IncidentOut = Schemas['IncidentOut'];
export type IncidentPage = Schemas['IncidentPage'];
export type IncidentCreate = Schemas['IncidentCreate'];
export type SearchAreaOut = Schemas['SearchAreaOut'];
export type SearchAreaPage = Schemas['SearchAreaPage'];
export type SearchAreaCreate = Schemas['SearchAreaCreate'];
export type PolygonGeoJSON = Schemas['PolygonGeoJSON'];
export type MissionOut = Schemas['MissionOut'];
export type MissionPage = Schemas['MissionPage'];
export type MissionCreate = Schemas['MissionCreate'];
export type MissionKind = Schemas['MissionKind'];
export type MissionStatus = Schemas['MissionStatus'];
export type WaypointIn = Schemas['WaypointIn'];
export type WaypointsOut = Schemas['WaypointsOut'];
export type PatternKind = Schemas['PatternKind'];
export type PlanRequest = Schemas['PlanRequest'];
export type PlanOut = Schemas['PlanOut'];
export type PlannedTask = Schemas['PlannedTask'];
export type MissionProgressOut = Schemas['MissionProgressOut'];
/** Mission progress on the `missions` WebSocket topic: the REST view without the geometry. */
export type MissionProgressView = Omit<MissionProgressOut, 'coverage_geometry'>;
export type TaskProgressView = Schemas['TaskProgressView'];
export type PoiView = Schemas['PoiView'];
export type PoiCreate = Schemas['PoiCreate'];
export type PoiPage = Schemas['PoiPage'];
export type PoiKind = Schemas['PoiKind'];
export type PoiStatus = Schemas['PoiStatus'];
export type PreflightReportView = Schemas['PreflightReportView'];
export type GeofenceOut = Schemas['GeofenceOut'];
export type GeofencePage = Schemas['GeofencePage'];
export type GeofenceCreate = Schemas['GeofenceCreate'];

/** Commands the console sends (the discriminated request bodies of POST /commands). */
export type CommandRequest =
  | Schemas['HoldCommand']
  | Schemas['ResumeCommand']
  | Schemas['ReturnCommand']
  | Schemas['LandCommand']
  | Schemas['ArmCommand']
  | Schemas['DisarmCommand']
  | Schemas['TakeoffCommand']
  | Schemas['GotoCommand']
  | Schemas['MissionStartCommand']
  | Schemas['MissionPauseCommand'];
