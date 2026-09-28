// Generated from docs/api/openapi.json by scripts/gen-api.ts. Do not edit by hand.
// Regenerate with: npm run gen:api

export interface paths {
    "/api/v1/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Health
         * @description Report that the service is up.
         */
        get: operations["health_api_v1_health_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/version": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Version
         * @description Report the service and API versions and the ground station's name.
         */
        get: operations["version_api_v1_version_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/login": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Login
         * @description Exchange a username and password for a session token.
         */
        post: operations["login_api_v1_auth_login_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/logout": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Logout
         * @description End the current session.
         */
        post: operations["logout_api_v1_auth_logout_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/me": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Me
         * @description Who am I, and what may I do.
         */
        get: operations["me_api_v1_auth_me_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/password": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Change Password
         * @description Change one's own password; every other session of this user is revoked.
         */
        post: operations["change_password_api_v1_auth_password_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/users": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Users
         * @description List accounts in creation order.
         */
        get: operations["list_users_api_v1_users_get"];
        put?: never;
        /**
         * Create User
         * @description Create an account.
         */
        post: operations["create_user_api_v1_users_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/users/{user_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get User
         * @description One account.
         */
        get: operations["get_user_api_v1_users__user_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /**
         * Update User
         * @description Change display name, role or active flag. Deactivation revokes the user's sessions.
         */
        patch: operations["update_user_api_v1_users__user_id__patch"];
        trace?: never;
    };
    "/api/v1/users/{user_id}/password": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Reset Password
         * @description Set a new password for a user and revoke all of their sessions.
         */
        post: operations["reset_password_api_v1_users__user_id__password_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/aircraft": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Aircraft
         * @description List registered aircraft in registration order.
         */
        get: operations["list_aircraft_api_v1_aircraft_get"];
        put?: never;
        /**
         * Create Aircraft
         * @description Register an aircraft.
         */
        post: operations["create_aircraft_api_v1_aircraft_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/aircraft/{aircraft_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Aircraft
         * @description One aircraft.
         */
        get: operations["get_aircraft_api_v1_aircraft__aircraft_id__get"];
        put?: never;
        post?: never;
        /**
         * Delete Aircraft
         * @description Remove an aircraft from the registry; refused while any task refers to it.
         */
        delete: operations["delete_aircraft_api_v1_aircraft__aircraft_id__delete"];
        options?: never;
        head?: never;
        /**
         * Update Aircraft
         * @description Change an aircraft's registration.
         */
        patch: operations["update_aircraft_api_v1_aircraft__aircraft_id__patch"];
        trace?: never;
    };
    "/api/v1/groups": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Groups
         * @description List groups.
         */
        get: operations["list_groups_api_v1_groups_get"];
        put?: never;
        /**
         * Create Group
         * @description Create a group.
         */
        post: operations["create_group_api_v1_groups_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/groups/{group_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Group
         * @description One group.
         */
        get: operations["get_group_api_v1_groups__group_id__get"];
        put?: never;
        post?: never;
        /**
         * Delete Group
         * @description Delete a group (its aircraft are unaffected).
         */
        delete: operations["delete_group_api_v1_groups__group_id__delete"];
        options?: never;
        head?: never;
        /**
         * Update Group
         * @description Rename a group or replace its members.
         */
        patch: operations["update_group_api_v1_groups__group_id__patch"];
        trace?: never;
    };
    "/api/v1/incidents": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Incidents
         * @description List incidents, optionally by status.
         */
        get: operations["list_incidents_api_v1_incidents_get"];
        put?: never;
        /**
         * Create Incident
         * @description Open an incident.
         */
        post: operations["create_incident_api_v1_incidents_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/incidents/{incident_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Incident
         * @description One incident.
         */
        get: operations["get_incident_api_v1_incidents__incident_id__get"];
        put?: never;
        post?: never;
        /**
         * Delete Incident
         * @description Delete an empty incident (for one opened by mistake); otherwise close it instead.
         */
        delete: operations["delete_incident_api_v1_incidents__incident_id__delete"];
        options?: never;
        head?: never;
        /**
         * Update Incident
         * @description Change an incident's details, operating area or status.
         */
        patch: operations["update_incident_api_v1_incidents__incident_id__patch"];
        trace?: never;
    };
    "/api/v1/search-areas": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Search Areas
         * @description List search areas, optionally of one incident.
         */
        get: operations["list_search_areas_api_v1_search_areas_get"];
        put?: never;
        /**
         * Create Search Area
         * @description Define a search area inside an open incident's operating area.
         */
        post: operations["create_search_area_api_v1_search_areas_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/search-areas/{area_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Search Area
         * @description One search area.
         */
        get: operations["get_search_area_api_v1_search_areas__area_id__get"];
        put?: never;
        post?: never;
        /**
         * Delete Search Area
         * @description Delete a search area that no mission uses.
         */
        delete: operations["delete_search_area_api_v1_search_areas__area_id__delete"];
        options?: never;
        head?: never;
        /**
         * Update Search Area
         * @description Change a search area; ground teams' results can be recorded through ``status``.
         */
        patch: operations["update_search_area_api_v1_search_areas__area_id__patch"];
        trace?: never;
    };
    "/api/v1/geofences": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Geofences
         * @description List geofences, optionally of one incident.
         */
        get: operations["list_geofences_api_v1_geofences_get"];
        put?: never;
        /**
         * Create Geofence
         * @description Define a geofence inside an open incident's operating area.
         */
        post: operations["create_geofence_api_v1_geofences_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/geofences/{geofence_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Geofence
         * @description One geofence.
         */
        get: operations["get_geofence_api_v1_geofences__geofence_id__get"];
        put?: never;
        post?: never;
        /**
         * Delete Geofence
         * @description Delete a geofence.
         */
        delete: operations["delete_geofence_api_v1_geofences__geofence_id__delete"];
        options?: never;
        head?: never;
        /**
         * Update Geofence
         * @description Change a geofence.
         */
        patch: operations["update_geofence_api_v1_geofences__geofence_id__patch"];
        trace?: never;
    };
    "/api/v1/missions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Missions
         * @description List missions, optionally by incident and status.
         */
        get: operations["list_missions_api_v1_missions_get"];
        put?: never;
        /**
         * Create Mission
         * @description Create a draft mission in an open incident.
         */
        post: operations["create_mission_api_v1_missions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/missions/{mission_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Mission
         * @description One mission.
         */
        get: operations["get_mission_api_v1_missions__mission_id__get"];
        put?: never;
        post?: never;
        /**
         * Delete Mission
         * @description Delete a draft mission with its waypoints and tasks; later missions are aborted instead.
         */
        delete: operations["delete_mission_api_v1_missions__mission_id__delete"];
        options?: never;
        head?: never;
        /**
         * Update Mission
         * @description Change a mission's plan, name or planning status.
         */
        patch: operations["update_mission_api_v1_missions__mission_id__patch"];
        trace?: never;
    };
    "/api/v1/missions/{mission_id}/waypoints": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Waypoints
         * @description A mission's route, in order.
         */
        get: operations["get_waypoints_api_v1_missions__mission_id__waypoints_get"];
        /**
         * Replace Waypoints
         * @description Replace a mission's whole route atomically.
         */
        put: operations["replace_waypoints_api_v1_missions__mission_id__waypoints_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tasks": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Tasks
         * @description List tasks, optionally by mission and aircraft.
         */
        get: operations["list_tasks_api_v1_tasks_get"];
        put?: never;
        /**
         * Create Task
         * @description Assign an aircraft to a mission that is being planned.
         */
        post: operations["create_task_api_v1_tasks_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tasks/{task_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Task
         * @description One task.
         */
        get: operations["get_task_api_v1_tasks__task_id__get"];
        put?: never;
        post?: never;
        /**
         * Delete Task
         * @description Remove an assignment while the mission is being planned.
         */
        delete: operations["delete_task_api_v1_tasks__task_id__delete"];
        options?: never;
        head?: never;
        /**
         * Update Task
         * @description Change a task's overrides, or cancel it.
         */
        patch: operations["update_task_api_v1_tasks__task_id__patch"];
        trace?: never;
    };
    "/api/v1/video-streams": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Video Streams
         * @description List video sources.
         */
        get: operations["list_video_streams_api_v1_video_streams_get"];
        put?: never;
        /**
         * Create Video Stream
         * @description Register a video source.
         */
        post: operations["create_video_stream_api_v1_video_streams_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video-streams/{stream_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Video Stream
         * @description One video source.
         */
        get: operations["get_video_stream_api_v1_video_streams__stream_id__get"];
        put?: never;
        post?: never;
        /**
         * Delete Video Stream
         * @description Remove a video source.
         */
        delete: operations["delete_video_stream_api_v1_video_streams__stream_id__delete"];
        options?: never;
        head?: never;
        /**
         * Update Video Stream
         * @description Change a video source.
         */
        patch: operations["update_video_stream_api_v1_video_streams__stream_id__patch"];
        trace?: never;
    };
    "/api/v1/audit": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Audit Events
         * @description Search the audit trail, newest first.
         */
        get: operations["list_audit_events_api_v1_audit_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /**
         * AircraftCreate
         * @description A new aircraft. Links may be added later; a task needs the matching link (ADR 0003).
         */
        AircraftCreate: {
            /**
             * Callsign
             * @description Radio callsign, stored upper-case; unique ignoring case.
             */
            callsign: string;
            airframe: components["schemas"]["Airframe"];
            /** Mavlink System Id */
            mavlink_system_id?: number | null;
            /** Mavlink Connection */
            mavlink_connection?: string | null;
            /** Swarm Drone Id */
            swarm_drone_id?: number | null;
            /** Cruise Speed Mps */
            cruise_speed_mps?: number | null;
            /** Notes */
            notes?: string | null;
        };
        /**
         * AircraftOut
         * @description A registered aircraft.
         */
        AircraftOut: {
            /** Id */
            id: string;
            /** Callsign */
            callsign: string;
            airframe: components["schemas"]["Airframe"];
            /** Mavlink System Id */
            mavlink_system_id: number | null;
            /** Mavlink Connection */
            mavlink_connection: string | null;
            /** Swarm Drone Id */
            swarm_drone_id: number | null;
            /** Cruise Speed Mps */
            cruise_speed_mps: number | null;
            /** Notes */
            notes: string | null;
            /** Group Ids */
            group_ids: string[];
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /**
         * AircraftPage
         * @description A page of aircraft.
         */
        AircraftPage: {
            /** Items */
            items: components["schemas"]["AircraftOut"][];
            /**
             * Next Cursor
             * @description Null when this is the last page.
             */
            next_cursor: string | null;
        };
        /**
         * AircraftUpdate
         * @description Fields to change; ``null`` clears a nullable field.
         */
        AircraftUpdate: {
            /**
             * Callsign
             * @description Radio callsign, stored upper-case; unique ignoring case.
             */
            callsign?: string;
            airframe?: components["schemas"]["Airframe"];
            /** Mavlink System Id */
            mavlink_system_id?: number | null;
            /** Mavlink Connection */
            mavlink_connection?: string | null;
            /** Swarm Drone Id */
            swarm_drone_id?: number | null;
            /** Cruise Speed Mps */
            cruise_speed_mps?: number | null;
            /** Notes */
            notes?: string | null;
        };
        /**
         * Airframe
         * @description Aircraft type; drives planning constraints (turn radius, hover ability).
         * @enum {string}
         */
        Airframe: "fixed_wing" | "multirotor_hexa" | "multirotor_quad";
        /**
         * AuditEventOut
         * @description One audit event, including its chain hashes.
         */
        AuditEventOut: {
            /** Seq */
            seq: number;
            /** Event Id */
            event_id: string;
            /**
             * Ts
             * Format: date-time
             */
            ts: string;
            /** Actor User Id */
            actor_user_id: string | null;
            /** Actor Username */
            actor_username: string | null;
            /** Action */
            action: string;
            /** Entity Type */
            entity_type: string | null;
            /** Entity Id */
            entity_id: string | null;
            /** Request Id */
            request_id: string | null;
            /** Source Ip */
            source_ip: string | null;
            /** Details */
            details: {
                [key: string]: unknown;
            };
            /** Prev Hash */
            prev_hash: string;
            /** Hash */
            hash: string;
        };
        /**
         * AuditPage
         * @description A page of audit events, newest first.
         */
        AuditPage: {
            /** Items */
            items: components["schemas"]["AuditEventOut"][];
            /**
             * Next Cursor
             * @description Null when this is the last page.
             */
            next_cursor: string | null;
        };
        /**
         * FieldError
         * @description One invalid input value.
         */
        FieldError: {
            /**
             * Loc
             * @description Where the value is: body, query, path, header.
             */
            loc: (string | number)[];
            /** Msg */
            msg: string;
            /** Type */
            type: string;
        };
        /**
         * GeoPoint
         * @description A WGS84 position with explicit keys (never a bare pair).
         */
        GeoPoint: {
            /** Latitude */
            latitude: number;
            /** Longitude */
            longitude: number;
        };
        /**
         * GeofenceCreate
         * @description A new geofence.
         */
        GeofenceCreate: {
            /** Incident Id */
            incident_id: string;
            /** Name */
            name: string;
            kind: components["schemas"]["GeofenceKind"];
            geometry: components["schemas"]["PolygonGeoJSON"];
            /** Max Altitude Relative M */
            max_altitude_relative_m?: number | null;
            /**
             * Enabled
             * @default true
             */
            enabled: boolean;
        };
        /**
         * GeofenceKind
         * @description Inclusion: aircraft must stay inside. Exclusion: aircraft must stay outside.
         * @enum {string}
         */
        GeofenceKind: "inclusion" | "exclusion";
        /**
         * GeofenceOut
         * @description An inclusion or exclusion zone.
         */
        GeofenceOut: {
            /** Id */
            id: string;
            /** Incident Id */
            incident_id: string;
            /** Name */
            name: string;
            kind: components["schemas"]["GeofenceKind"];
            geometry: components["schemas"]["PolygonGeoJSON"];
            /** Max Altitude Relative M */
            max_altitude_relative_m: number | null;
            /** Enabled */
            enabled: boolean;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /**
         * GeofencePage
         * @description A page of geofences.
         */
        GeofencePage: {
            /** Items */
            items: components["schemas"]["GeofenceOut"][];
            /**
             * Next Cursor
             * @description Null when this is the last page.
             */
            next_cursor: string | null;
        };
        /**
         * GeofenceUpdate
         * @description Fields to change.
         */
        GeofenceUpdate: {
            /** Name */
            name?: string;
            kind?: components["schemas"]["GeofenceKind"];
            geometry?: components["schemas"]["PolygonGeoJSON"];
            /** Max Altitude Relative M */
            max_altitude_relative_m?: number | null;
            /** Enabled */
            enabled?: boolean;
        };
        /**
         * GroupCreate
         * @description A new group.
         */
        GroupCreate: {
            /** Name */
            name: string;
            /** Description */
            description?: string | null;
            /** Aircraft Ids */
            aircraft_ids?: string[];
        };
        /**
         * GroupOut
         * @description A named set of aircraft.
         */
        GroupOut: {
            /** Id */
            id: string;
            /** Name */
            name: string;
            /** Description */
            description: string | null;
            /** Aircraft Ids */
            aircraft_ids: string[];
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /**
         * GroupPage
         * @description A page of groups.
         */
        GroupPage: {
            /** Items */
            items: components["schemas"]["GroupOut"][];
            /**
             * Next Cursor
             * @description Null when this is the last page.
             */
            next_cursor: string | null;
        };
        /**
         * GroupUpdate
         * @description Fields to change; ``aircraft_ids`` replaces the whole membership.
         */
        GroupUpdate: {
            /** Name */
            name?: string;
            /** Description */
            description?: string | null;
            /** Aircraft Ids */
            aircraft_ids?: string[];
        };
        /**
         * Health
         * @description Liveness of the service. ``server_time`` lets clients detect clock skew.
         */
        Health: {
            /**
             * Status
             * @constant
             */
            status: "ok";
            /**
             * Server Time
             * Format: date-time
             */
            server_time: string;
        };
        /**
         * IncidentCreate
         * @description A new incident; it starts ``active``.
         */
        IncidentCreate: {
            /** Name */
            name: string;
            /** Description */
            description?: string | null;
            base: components["schemas"]["GeoPoint"];
            /** Base Altitude Amsl M */
            base_altitude_amsl_m?: number | null;
            /**
             * Operating Radius M
             * @description Every geometry of the incident must lie within this distance of the base.
             * @default 25000
             */
            operating_radius_m: number;
        };
        /**
         * IncidentOut
         * @description A SAR incident.
         */
        IncidentOut: {
            /** Id */
            id: string;
            /** Name */
            name: string;
            /** Description */
            description: string | null;
            status: components["schemas"]["IncidentStatus"];
            base: components["schemas"]["GeoPoint"];
            /** Base Altitude Amsl M */
            base_altitude_amsl_m: number | null;
            /** Operating Radius M */
            operating_radius_m: number;
            /** Created By */
            created_by: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /** Closed At */
            closed_at: string | null;
        };
        /**
         * IncidentPage
         * @description A page of incidents.
         */
        IncidentPage: {
            /** Items */
            items: components["schemas"]["IncidentOut"][];
            /**
             * Next Cursor
             * @description Null when this is the last page.
             */
            next_cursor: string | null;
        };
        /**
         * IncidentStatus
         * @description Lifecycle of an incident; ``closed`` is terminal and read-only.
         * @enum {string}
         */
        IncidentStatus: "active" | "suspended" | "closed";
        /**
         * IncidentUpdate
         * @description Fields to change. ``closed`` is terminal; moving the base or shrinking the radius
         *     is refused while any geometry of the incident would end up outside.
         */
        IncidentUpdate: {
            /** Name */
            name?: string;
            /** Description */
            description?: string | null;
            base?: components["schemas"]["GeoPoint"];
            /** Base Altitude Amsl M */
            base_altitude_amsl_m?: number | null;
            /**
             * Operating Radius M
             * @description Every geometry of the incident must lie within this distance of the base.
             */
            operating_radius_m?: number;
            status?: components["schemas"]["IncidentStatus"];
        };
        /**
         * LoginRequest
         * @description Credentials. The username is case-insensitive.
         */
        LoginRequest: {
            /** Username */
            username: string;
            /** Password */
            password: string;
        };
        /**
         * LoginResponse
         * @description A new session. The token is shown only here; send it as ``Authorization: Bearer``.
         */
        LoginResponse: {
            /** Token */
            token: string;
            /**
             * Token Type
             * @constant
             */
            token_type: "bearer";
            /**
             * Expires At
             * Format: date-time
             */
            expires_at: string;
            user: components["schemas"]["UserOut"];
            /** Permissions */
            permissions: components["schemas"]["Permission"][];
        };
        /**
         * MeResponse
         * @description The current session's user and what they may do.
         */
        MeResponse: {
            user: components["schemas"]["UserOut"];
            /** Permissions */
            permissions: components["schemas"]["Permission"][];
            /**
             * Session Expires At
             * Format: date-time
             */
            session_expires_at: string;
        };
        /**
         * MissionCreate
         * @description A new mission; it starts as ``draft``. Area missions need a search area.
         */
        MissionCreate: {
            /** Incident Id */
            incident_id: string;
            /** Name */
            name: string;
            kind: components["schemas"]["MissionKind"];
            /** Search Area Id */
            search_area_id?: string | null;
            /**
             * Default Altitude Relative M
             * @description Default altitude above each aircraft's home (ADR 0014).
             */
            default_altitude_relative_m: number;
            /** Default Speed Mps */
            default_speed_mps?: number | null;
            /** Notes */
            notes?: string | null;
        };
        /**
         * MissionKind
         * @description Waypoint route, GCS-planned area search (model A), swarm area search (model B, ADR 0003).
         * @enum {string}
         */
        MissionKind: "waypoint" | "area_search" | "swarm_area";
        /**
         * MissionOut
         * @description A mission.
         */
        MissionOut: {
            /** Id */
            id: string;
            /** Incident Id */
            incident_id: string;
            /** Name */
            name: string;
            kind: components["schemas"]["MissionKind"];
            status: components["schemas"]["MissionStatus"];
            /** Search Area Id */
            search_area_id: string | null;
            /** Default Altitude Relative M */
            default_altitude_relative_m: number;
            /** Default Speed Mps */
            default_speed_mps: number | null;
            /** Notes */
            notes: string | null;
            /** Waypoint Count */
            waypoint_count: number;
            /** Created By */
            created_by: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /**
         * MissionPage
         * @description A page of missions.
         */
        MissionPage: {
            /** Items */
            items: components["schemas"]["MissionOut"][];
            /**
             * Next Cursor
             * @description Null when this is the last page.
             */
            next_cursor: string | null;
        };
        /**
         * MissionStatus
         * @description Mission lifecycle. ``active``, ``paused`` and ``completed`` are set by execution only.
         * @enum {string}
         */
        MissionStatus: "draft" | "planned" | "active" | "paused" | "completed" | "aborted";
        /**
         * MissionUpdate
         * @description Fields to change. Plan fields change only in draft/planned; ``status`` may go
         *     draft↔planned or to aborted.
         */
        MissionUpdate: {
            /** Name */
            name?: string;
            /** Notes */
            notes?: string | null;
            /** Search Area Id */
            search_area_id?: string | null;
            /**
             * Default Altitude Relative M
             * @description Default altitude above each aircraft's home (ADR 0014).
             */
            default_altitude_relative_m?: number;
            /** Default Speed Mps */
            default_speed_mps?: number | null;
            status?: components["schemas"]["MissionStatus"];
        };
        /**
         * PasswordChange
         * @description Change one's own password; other sessions of the user are revoked.
         */
        PasswordChange: {
            /** Current Password */
            current_password: string;
            /** New Password */
            new_password: string;
        };
        /**
         * PasswordReset
         * @description An administrator sets a new password; the user's sessions are revoked.
         */
        PasswordReset: {
            /** New Password */
            new_password: string;
        };
        /**
         * Permission
         * @description Something a session may be allowed to do.
         * @enum {string}
         */
        Permission: "fleet.view" | "missions.plan" | "fleet.manage" | "incidents.manage" | "geofences.manage" | "users.view" | "audit.read" | "users.manage";
        /**
         * PolygonGeoJSON
         * @description A GeoJSON Polygon with one ring (no holes), 3 to 256 distinct vertices, valid
         *     (not self-intersecting, non-zero area), normalized to a counter-clockwise ring.
         */
        PolygonGeoJSON: {
            /**
             * Type
             * @constant
             */
            type: "Polygon";
            /**
             * Coordinates
             * @description Exactly one closed ring of [longitude, latitude] positions (RFC 7946).
             */
            coordinates: [
                number,
                number
            ][][];
        };
        /**
         * Problem
         * @description RFC 9457 problem details. Extension members depend on ``type``.
         */
        Problem: {
            /**
             * Type
             * @default about:blank
             * @example urn:sar-gcs:problem:conflict
             */
            type: string;
            /** Title */
            title: string;
            /** Status */
            status: number;
            /** Detail */
            detail?: string | null;
            /** Instance */
            instance?: string | null;
            /**
             * Errors
             * @description Present on validation errors: each invalid value.
             */
            errors?: components["schemas"]["FieldError"][] | null;
        } & {
            [key: string]: unknown;
        };
        /**
         * Role
         * @description Operator roles, lowest to highest authority (ADR 0009).
         * @enum {string}
         */
        Role: "observer" | "operator" | "supervisor" | "admin";
        /**
         * SearchAreaCreate
         * @description A new search area; it starts ``unassigned``.
         */
        SearchAreaCreate: {
            /** Incident Id */
            incident_id: string;
            /** Name */
            name: string;
            geometry: components["schemas"]["PolygonGeoJSON"];
            /**
             * Priority
             * @description 1 is the highest priority.
             * @default 3
             */
            priority: number;
            /** Notes */
            notes?: string | null;
        };
        /**
         * SearchAreaOut
         * @description An area to be searched.
         */
        SearchAreaOut: {
            /** Id */
            id: string;
            /** Incident Id */
            incident_id: string;
            /** Name */
            name: string;
            geometry: components["schemas"]["PolygonGeoJSON"];
            /** Area M2 */
            area_m2: number;
            /** Priority */
            priority: number;
            status: components["schemas"]["SearchAreaStatus"];
            /** Notes */
            notes: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /**
         * SearchAreaPage
         * @description A page of search areas.
         */
        SearchAreaPage: {
            /** Items */
            items: components["schemas"]["SearchAreaOut"][];
            /**
             * Next Cursor
             * @description Null when this is the last page.
             */
            next_cursor: string | null;
        };
        /**
         * SearchAreaStatus
         * @description Search progress of an area; set by operators (ground teams too) or, from M4, missions.
         * @enum {string}
         */
        SearchAreaStatus: "unassigned" | "assigned" | "in_progress" | "searched";
        /**
         * SearchAreaUpdate
         * @description Fields to change. The geometry is frozen while a running mission uses the area.
         */
        SearchAreaUpdate: {
            /** Name */
            name?: string;
            geometry?: components["schemas"]["PolygonGeoJSON"];
            /**
             * Priority
             * @description 1 is the highest priority.
             */
            priority?: number;
            status?: components["schemas"]["SearchAreaStatus"];
            /** Notes */
            notes?: string | null;
        };
        /**
         * TaskCreate
         * @description Assign an aircraft to a mission, optionally overriding its defaults.
         */
        TaskCreate: {
            /** Mission Id */
            mission_id: string;
            /** Aircraft Id */
            aircraft_id: string;
            /** Altitude Relative M */
            altitude_relative_m?: number | null;
            /** Speed Mps */
            speed_mps?: number | null;
            /** Start Delay S */
            start_delay_s?: number | null;
        };
        /**
         * TaskOut
         * @description An aircraft's assignment to a mission.
         */
        TaskOut: {
            /** Id */
            id: string;
            /** Mission Id */
            mission_id: string;
            /** Aircraft Id */
            aircraft_id: string;
            status: components["schemas"]["TaskStatus"];
            /** Altitude Relative M */
            altitude_relative_m: number | null;
            /** Speed Mps */
            speed_mps: number | null;
            /** Start Delay S */
            start_delay_s: number | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /**
         * TaskPage
         * @description A page of tasks.
         */
        TaskPage: {
            /** Items */
            items: components["schemas"]["TaskOut"][];
            /**
             * Next Cursor
             * @description Null when this is the last page.
             */
            next_cursor: string | null;
        };
        /**
         * TaskStatus
         * @description An aircraft's assignment to a mission.
         * @enum {string}
         */
        TaskStatus: "pending" | "active" | "completed" | "failed" | "cancelled";
        /**
         * TaskUpdate
         * @description Overrides change only while the mission is being planned; ``status`` may go to cancelled.
         */
        TaskUpdate: {
            /** Altitude Relative M */
            altitude_relative_m?: number | null;
            /** Speed Mps */
            speed_mps?: number | null;
            /** Start Delay S */
            start_delay_s?: number | null;
            status?: components["schemas"]["TaskStatus"];
        };
        /**
         * UserCreate
         * @description A new account. The username is stored lower-case.
         */
        UserCreate: {
            /** Username */
            username: string;
            /** Display Name */
            display_name: string;
            role: components["schemas"]["Role"];
            /** Password */
            password: string;
        };
        /**
         * UserOut
         * @description An operator account (never includes credentials).
         */
        UserOut: {
            /** Id */
            id: string;
            /** Username */
            username: string;
            /** Display Name */
            display_name: string;
            role: components["schemas"]["Role"];
            /** Is Active */
            is_active: boolean;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /** Last Login At */
            last_login_at: string | null;
        };
        /**
         * UserPage
         * @description A page of users.
         */
        UserPage: {
            /** Items */
            items: components["schemas"]["UserOut"][];
            /**
             * Next Cursor
             * @description Null when this is the last page.
             */
            next_cursor: string | null;
        };
        /**
         * UserUpdate
         * @description Fields to change; omitted fields are unchanged.
         */
        UserUpdate: {
            /** Display Name */
            display_name?: string;
            role?: components["schemas"]["Role"];
            /** Is Active */
            is_active?: boolean;
        };
        /**
         * VersionInfo
         * @description What is running, for operators and bug reports.
         */
        VersionInfo: {
            /**
             * Service
             * @constant
             */
            service: "fleet-service";
            /** Version */
            version: string;
            /** Api Version */
            api_version: string;
            /** Station Name */
            station_name: string;
        };
        /**
         * VideoCodec
         * @description Codec of a video source (ADR 0012: H.264 is the baseline).
         * @enum {string}
         */
        VideoCodec: "h264" | "h265" | "unknown";
        /**
         * VideoStreamCreate
         * @description A new video source. ``relay_path`` is its path on the video relay.
         */
        VideoStreamCreate: {
            /** Aircraft Id */
            aircraft_id?: string | null;
            /** Name */
            name: string;
            /** Source Url */
            source_url: string;
            /** Relay Path */
            relay_path: string;
            /** @default h264 */
            codec: components["schemas"]["VideoCodec"];
            /**
             * Enabled
             * @default true
             */
            enabled: boolean;
        };
        /**
         * VideoStreamOut
         * @description A video source; the source URL's password is redacted.
         */
        VideoStreamOut: {
            /** Id */
            id: string;
            /** Aircraft Id */
            aircraft_id: string | null;
            /** Name */
            name: string;
            /** Source Url */
            source_url: string;
            /** Relay Path */
            relay_path: string;
            codec: components["schemas"]["VideoCodec"];
            /** Enabled */
            enabled: boolean;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /**
         * VideoStreamPage
         * @description A page of video streams.
         */
        VideoStreamPage: {
            /** Items */
            items: components["schemas"]["VideoStreamOut"][];
            /**
             * Next Cursor
             * @description Null when this is the last page.
             */
            next_cursor: string | null;
        };
        /**
         * VideoStreamUpdate
         * @description Fields to change.
         */
        VideoStreamUpdate: {
            /** Aircraft Id */
            aircraft_id?: string | null;
            /** Name */
            name?: string;
            /** Source Url */
            source_url?: string;
            /** Relay Path */
            relay_path?: string;
            codec?: components["schemas"]["VideoCodec"];
            /** Enabled */
            enabled?: boolean;
        };
        /**
         * WaypointIn
         * @description One route point.
         */
        WaypointIn: {
            /** Latitude */
            latitude: number;
            /** Longitude */
            longitude: number;
            /**
             * Altitude Relative M
             * @description Metres above each aircraft's home position (ADR 0014).
             */
            altitude_relative_m: number;
            /** Speed Mps */
            speed_mps?: number | null;
            /** Loiter S */
            loiter_s?: number | null;
        };
        /**
         * WaypointOut
         * @description One route point and its position in the route.
         */
        WaypointOut: {
            /** Seq */
            seq: number;
            /** Latitude */
            latitude: number;
            /** Longitude */
            longitude: number;
            /** Altitude Relative M */
            altitude_relative_m: number;
            /** Speed Mps */
            speed_mps: number | null;
            /** Loiter S */
            loiter_s: number | null;
        };
        /**
         * WaypointsIn
         * @description The complete, ordered route (replaces the previous one).
         */
        WaypointsIn: {
            /** Waypoints */
            waypoints: components["schemas"]["WaypointIn"][];
        };
        /**
         * WaypointsOut
         * @description A mission's route.
         */
        WaypointsOut: {
            /** Mission Id */
            mission_id: string;
            /** Waypoints */
            waypoints: components["schemas"]["WaypointOut"][];
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    health_api_v1_health_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Health"];
                };
            };
        };
    };
    version_api_v1_version_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VersionInfo"];
                };
            };
        };
    };
    login_api_v1_auth_login_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LoginRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LoginResponse"];
                };
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Too many attempts; see Retry-After. */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    logout_api_v1_auth_logout_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    me_api_v1_auth_me_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MeResponse"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    change_password_api_v1_auth_password_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PasswordChange"];
            };
        };
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    list_users_api_v1_users_get: {
        parameters: {
            query?: {
                /** @description Maximum items to return. */
                limit?: number;
                /** @description Opaque cursor from a previous page's next_cursor. */
                cursor?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserPage"];
                };
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    create_user_api_v1_users_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UserCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserOut"];
                };
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    get_user_api_v1_users__user_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserOut"];
                };
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    update_user_api_v1_users__user_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UserUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserOut"];
                };
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    reset_password_api_v1_users__user_id__password_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PasswordReset"];
            };
        };
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    list_aircraft_api_v1_aircraft_get: {
        parameters: {
            query?: {
                /** @description Maximum items to return. */
                limit?: number;
                /** @description Opaque cursor from a previous page's next_cursor. */
                cursor?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AircraftPage"];
                };
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    create_aircraft_api_v1_aircraft_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AircraftCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AircraftOut"];
                };
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    get_aircraft_api_v1_aircraft__aircraft_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                aircraft_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AircraftOut"];
                };
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    delete_aircraft_api_v1_aircraft__aircraft_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                aircraft_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    update_aircraft_api_v1_aircraft__aircraft_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                aircraft_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AircraftUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AircraftOut"];
                };
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    list_groups_api_v1_groups_get: {
        parameters: {
            query?: {
                /** @description Maximum items to return. */
                limit?: number;
                /** @description Opaque cursor from a previous page's next_cursor. */
                cursor?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GroupPage"];
                };
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    create_group_api_v1_groups_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["GroupCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GroupOut"];
                };
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    get_group_api_v1_groups__group_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                group_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GroupOut"];
                };
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    delete_group_api_v1_groups__group_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                group_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    update_group_api_v1_groups__group_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                group_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["GroupUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GroupOut"];
                };
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    list_incidents_api_v1_incidents_get: {
        parameters: {
            query?: {
                status?: components["schemas"]["IncidentStatus"] | null;
                /** @description Maximum items to return. */
                limit?: number;
                /** @description Opaque cursor from a previous page's next_cursor. */
                cursor?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IncidentPage"];
                };
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    create_incident_api_v1_incidents_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["IncidentCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IncidentOut"];
                };
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    get_incident_api_v1_incidents__incident_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                incident_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IncidentOut"];
                };
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    delete_incident_api_v1_incidents__incident_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                incident_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    update_incident_api_v1_incidents__incident_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                incident_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["IncidentUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IncidentOut"];
                };
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    list_search_areas_api_v1_search_areas_get: {
        parameters: {
            query?: {
                incident_id?: string | null;
                /** @description Maximum items to return. */
                limit?: number;
                /** @description Opaque cursor from a previous page's next_cursor. */
                cursor?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SearchAreaPage"];
                };
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    create_search_area_api_v1_search_areas_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SearchAreaCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SearchAreaOut"];
                };
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    get_search_area_api_v1_search_areas__area_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                area_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SearchAreaOut"];
                };
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    delete_search_area_api_v1_search_areas__area_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                area_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    update_search_area_api_v1_search_areas__area_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                area_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SearchAreaUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SearchAreaOut"];
                };
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    list_geofences_api_v1_geofences_get: {
        parameters: {
            query?: {
                incident_id?: string | null;
                /** @description Maximum items to return. */
                limit?: number;
                /** @description Opaque cursor from a previous page's next_cursor. */
                cursor?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GeofencePage"];
                };
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    create_geofence_api_v1_geofences_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["GeofenceCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GeofenceOut"];
                };
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    get_geofence_api_v1_geofences__geofence_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                geofence_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GeofenceOut"];
                };
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    delete_geofence_api_v1_geofences__geofence_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                geofence_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    update_geofence_api_v1_geofences__geofence_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                geofence_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["GeofenceUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GeofenceOut"];
                };
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    list_missions_api_v1_missions_get: {
        parameters: {
            query?: {
                incident_id?: string | null;
                status?: components["schemas"]["MissionStatus"] | null;
                /** @description Maximum items to return. */
                limit?: number;
                /** @description Opaque cursor from a previous page's next_cursor. */
                cursor?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MissionPage"];
                };
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    create_mission_api_v1_missions_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MissionCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MissionOut"];
                };
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    get_mission_api_v1_missions__mission_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                mission_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MissionOut"];
                };
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    delete_mission_api_v1_missions__mission_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                mission_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    update_mission_api_v1_missions__mission_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                mission_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MissionUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MissionOut"];
                };
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    get_waypoints_api_v1_missions__mission_id__waypoints_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                mission_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WaypointsOut"];
                };
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    replace_waypoints_api_v1_missions__mission_id__waypoints_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                mission_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WaypointsIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WaypointsOut"];
                };
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    list_tasks_api_v1_tasks_get: {
        parameters: {
            query?: {
                mission_id?: string | null;
                aircraft_id?: string | null;
                /** @description Maximum items to return. */
                limit?: number;
                /** @description Opaque cursor from a previous page's next_cursor. */
                cursor?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TaskPage"];
                };
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    create_task_api_v1_tasks_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TaskCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TaskOut"];
                };
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    get_task_api_v1_tasks__task_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TaskOut"];
                };
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    delete_task_api_v1_tasks__task_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    update_task_api_v1_tasks__task_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TaskUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TaskOut"];
                };
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    list_video_streams_api_v1_video_streams_get: {
        parameters: {
            query?: {
                /** @description Maximum items to return. */
                limit?: number;
                /** @description Opaque cursor from a previous page's next_cursor. */
                cursor?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoStreamPage"];
                };
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    create_video_stream_api_v1_video_streams_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["VideoStreamCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoStreamOut"];
                };
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    get_video_stream_api_v1_video_streams__stream_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                stream_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoStreamOut"];
                };
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    delete_video_stream_api_v1_video_streams__stream_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                stream_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    update_video_stream_api_v1_video_streams__stream_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                stream_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["VideoStreamUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoStreamOut"];
                };
            };
            /** @description The request body could not be parsed (not valid JSON or not UTF-8). */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The resource does not exist. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The request conflicts with the current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
    list_audit_events_api_v1_audit_get: {
        parameters: {
            query?: {
                actor_user_id?: string | null;
                /** @description Prefix, e.g. 'auth.' or 'mission.update'. */
                action?: string | null;
                entity_type?: string | null;
                entity_id?: string | null;
                since?: string | null;
                until?: string | null;
                /** @description Maximum items to return. */
                limit?: number;
                /** @description Opaque cursor from a previous page's next_cursor. */
                cursor?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuditPage"];
                };
            };
            /** @description Missing, invalid or expired session. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description The session's role lacks the required permission. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
            /** @description Invalid input: malformed, out of range, or semantically invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
}
