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

/** Commands the console sends (the discriminated request bodies of POST /commands). */
export type CommandRequest =
  | Schemas['HoldCommand']
  | Schemas['ResumeCommand']
  | Schemas['ReturnCommand']
  | Schemas['LandCommand']
  | Schemas['ArmCommand']
  | Schemas['DisarmCommand']
  | Schemas['TakeoffCommand']
  | Schemas['GotoCommand'];
