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
    "/api/v1/incidents/{incident_id}/export": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Export Incident
         * @description Everything about one incident in a zip (M6): areas, missions, POIs, alerts, commands,
         *     the audit events of its span with the chain's verification, and the telemetry of the
         *     aircraft involved; a manifest lists each file's SHA-256. The export is audited.
         */
        get: operations["export_incident_api_v1_incidents__incident_id__export_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
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
    "/api/v1/missions/{mission_id}/plan": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Plan
         * @description The saved plan of a mission.
         */
        get: operations["get_plan_api_v1_missions__mission_id__plan_get"];
        put?: never;
        /**
         * Plan
         * @description Plan a mission: routes for its aircraft, split, layered, sequenced and checked.
         */
        post: operations["plan_api_v1_missions__mission_id__plan_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/missions/{mission_id}/progress": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Progress
         * @description Progress of a mission: status, per-aircraft item, coverage and its geometry.
         */
        get: operations["get_progress_api_v1_missions__mission_id__progress_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/incidents/{incident_id}/pois": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Pois
         * @description An incident's points of interest, optionally by status.
         */
        get: operations["list_pois_api_v1_incidents__incident_id__pois_get"];
        put?: never;
        /**
         * Create Poi
         * @description Mark a point of interest in an open incident.
         */
        post: operations["create_poi_api_v1_incidents__incident_id__pois_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/pois/{poi_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Poi
         * @description One point of interest.
         */
        get: operations["get_poi_api_v1_pois__poi_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /**
         * Update Poi
         * @description Confirm, dismiss or resolve a point, change its kind, or add notes.
         */
        patch: operations["update_poi_api_v1_pois__poi_id__patch"];
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
    "/api/v1/video-streams/{stream_id}/view": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * View Video Stream
         * @description Start viewing a stream: its playback URLs; the viewing is audited (ADR 0012).
         */
        post: operations["view_video_stream_api_v1_video_streams__stream_id__view_post"];
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
    "/api/v1/video-health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Video Health
         * @description Each stream's state at the relay: live, stalled, offline or unknown.
         */
        get: operations["video_health_api_v1_video_health_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/presence": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Presence
         * @description Who is connected: users whose console was heard in the last 30 seconds.
         */
        get: operations["list_presence_api_v1_presence_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/fleet/state": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Fleet State
         * @description Every registered aircraft's link, latest telemetry and controller.
         */
        get: operations["fleet_state_api_v1_fleet_state_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/aircraft/{aircraft_id}/telemetry": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Telemetry History
         * @description Recorded telemetry of an aircraft (1 sample per second by default).
         */
        get: operations["telemetry_history_api_v1_aircraft__aircraft_id__telemetry_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/aircraft/{aircraft_id}/preflight": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Preflight Report
         * @description The last preflight check of an aircraft's failsafe parameters (arm and takeoff run
         *     one when theirs is older than a few minutes).
         */
        get: operations["preflight_report_api_v1_aircraft__aircraft_id__preflight_get"];
        put?: never;
        /**
         * Run Preflight
         * @description Read the aircraft's failsafe parameters now and check them (may take seconds).
         */
        post: operations["run_preflight_api_v1_aircraft__aircraft_id__preflight_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/simulation/aircraft/{aircraft_id}/faults": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Inject Fault
         * @description Simulation mode only: take a simulated aircraft's link or GNSS away, or set its battery.
         */
        post: operations["inject_fault_api_v1_simulation_aircraft__aircraft_id__faults_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/commands": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Commands
         * @description The most recent commands.
         */
        get: operations["list_commands_api_v1_commands_get"];
        put?: never;
        /**
         * Submit Command
         * @description Send a command to one or more aircraft; the answer lists every aircraft's outcome.
         */
        post: operations["submit_command_api_v1_commands_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/commands/{command_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Command
         * @description One command and its per-aircraft outcome.
         */
        get: operations["get_command_api_v1_commands__command_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/control-leases": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Leases
         * @description Who controls which aircraft.
         */
        get: operations["list_leases_api_v1_control_leases_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/aircraft/{aircraft_id}/control": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Assign Control
         * @description Supervisor: assign or force control (``user_id`` null releases it). Needs a reason.
         */
        put: operations["assign_control_api_v1_aircraft__aircraft_id__control_put"];
        /**
         * Take Control
         * @description Take control of an aircraft nobody controls.
         */
        post: operations["take_control_api_v1_aircraft__aircraft_id__control_post"];
        /**
         * Release Control
         * @description Give up control of an aircraft you control.
         */
        delete: operations["release_control_api_v1_aircraft__aircraft_id__control_delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/aircraft/{aircraft_id}/control/handover": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Request Handover
         * @description Ask the controlling operator to hand the aircraft over (expires if unanswered).
         */
        post: operations["request_handover_api_v1_aircraft__aircraft_id__control_handover_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/aircraft/{aircraft_id}/control/handover/accept": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Accept Handover
         * @description Controller: hand the aircraft to the operator who asked.
         */
        post: operations["accept_handover_api_v1_aircraft__aircraft_id__control_handover_accept_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/aircraft/{aircraft_id}/control/handover/decline": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Decline Handover
         * @description Controller: keep the aircraft.
         */
        post: operations["decline_handover_api_v1_aircraft__aircraft_id__control_handover_decline_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/alerts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Alerts
         * @description Alerts, newest first; filter by state (e.g. ``active``) and aircraft.
         */
        get: operations["list_alerts_api_v1_alerts_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/alerts/{alert_id}/acknowledge": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Acknowledge Alert
         * @description Mark an alert as seen. Event alerts (e.g. a command timeout) are closed by this.
         */
        post: operations["acknowledge_alert_api_v1_alerts__alert_id__acknowledge_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
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
    "/api/v1/audit/verify": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Verify Audit Chain
         * @description Re-walk the whole chain: the first inconsistency, or the head if intact. The heads
         *     exported outside the database must all still be in it (truncation, M6).
         */
        get: operations["verify_audit_chain_api_v1_audit_verify_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/audit/export": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Export Audit Events
         * @description Export the selected events (oldest first); the export itself is audited.
         */
        get: operations["export_audit_events_api_v1_audit_export_get"];
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
            /** Endurance S */
            endurance_s?: number | null;
            /** Notes */
            notes?: string | null;
        };
        /**
         * AircraftLive
         * @description One aircraft's live state: link, latest telemetry, controller.
         */
        AircraftLive: {
            /** Aircraft Id */
            aircraft_id: string;
            /** Callsign */
            callsign: string;
            airframe: components["schemas"]["Airframe"];
            link: components["schemas"]["LinkState"];
            /**
             * Links
             * @description Per-link state of an aircraft with a MAVLink and a swarm link (ADR 0025); empty otherwise, where ``link`` says it all.
             */
            links: {
                [key: string]: components["schemas"]["LinkState"];
            };
            /** Last Seen At */
            last_seen_at: string | null;
            telemetry: components["schemas"]["TelemetryView"] | null;
            controller: components["schemas"]["LeaseView"] | null;
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
            /** Endurance S */
            endurance_s: number | null;
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
            /** Endurance S */
            endurance_s?: number | null;
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
         * AlertKind
         * @description What an alert is about (engine from M1b/M4).
         * @enum {string}
         */
        AlertKind: "link_stale" | "link_lost" | "battery_low" | "battery_critical" | "gps_lost" | "geofence_breach" | "mission_complete" | "route_deviation" | "deconfliction_risk" | "command_timeout" | "command_unverified" | "control_orphaned" | "video_down" | "survivor_sighting" | "return_energy" | "link_partial" | "disk_low";
        /**
         * AlertPage
         * @description A page of alerts, newest first.
         */
        AlertPage: {
            /** Items */
            items: components["schemas"]["AlertView"][];
            /**
             * Next Cursor
             * @description Null when this is the last page.
             */
            next_cursor: string | null;
        };
        /**
         * AlertSeverity
         * @description How urgently an operator must look.
         * @enum {string}
         */
        AlertSeverity: "info" | "warning" | "critical";
        /**
         * AlertState
         * @description Alert lifecycle.
         * @enum {string}
         */
        AlertState: "active" | "acknowledged" | "cleared";
        /**
         * AlertView
         * @description An operator-facing alert.
         */
        AlertView: {
            /** Id */
            id: string;
            kind: components["schemas"]["AlertKind"];
            severity: components["schemas"]["AlertSeverity"];
            state: components["schemas"]["AlertState"];
            /** Aircraft Id */
            aircraft_id: string | null;
            /** Message */
            message: string;
            /**
             * Raised At
             * Format: date-time
             */
            raised_at: string;
            /** Acknowledged By */
            acknowledged_by: string | null;
            /** Acknowledged At */
            acknowledged_at: string | null;
            /** Cleared At */
            cleared_at: string | null;
            /**
             * Escalated At
             * @description When an unacknowledged warning became critical.
             */
            escalated_at?: string | null;
        };
        /**
         * ArmCommand
         * @description Arm the motors (on the ground). Always confirmed.
         */
        ArmCommand: {
            /**
             * Command Id
             * Format: uuid
             * @description Client-generated; the idempotency key.
             */
            command_id: string;
            /** Aircraft Ids */
            aircraft_ids: string[];
            /**
             * Confirmation Token
             * @description From a 428 answer to this exact request.
             */
            confirmation_token?: string | null;
            /**
             * Kind
             * @constant
             */
            kind: "arm";
        };
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
         * ChainStatus
         * @description Whether the audit hash chain is intact, and its head (to record elsewhere).
         */
        ChainStatus: {
            /** Ok */
            ok: boolean;
            /** Events */
            events: number;
            /** Head Seq */
            head_seq: number | null;
            /** Head Hash */
            head_hash: string | null;
            /** Broken At Seq */
            broken_at_seq: number | null;
            /** Reason */
            reason: string | null;
            /**
             * Exported Heads
             * @description Heads recorded outside the database (M6); each was found in the chain unless ``reason`` says otherwise.
             */
            exported_heads: number;
            /**
             * Verified At
             * Format: date-time
             */
            verified_at: string;
        };
        /**
         * CommandKind
         * @description Commands the GCS can send (ADR 0002 scope; no flight termination).
         * @enum {string}
         */
        CommandKind: "arm" | "disarm" | "takeoff" | "hold" | "resume" | "return_to_launch" | "land" | "goto" | "mission_upload" | "mission_start" | "mission_pause" | "geofence_upload";
        /**
         * CommandList
         * @description Recent commands, newest first.
         */
        CommandList: {
            /** Items */
            items: components["schemas"]["CommandView"][];
        };
        /**
         * CommandState
         * @description Overall state of a (possibly bulk) command (ADR 0011).
         * @enum {string}
         */
        CommandState: "awaiting_confirmation" | "in_progress" | "completed" | "rejected" | "expired";
        /**
         * CommandTargetState
         * @description Outcome of a command for one aircraft.
         * @enum {string}
         */
        CommandTargetState: "pending" | "dispatched" | "acked" | "nacked" | "timeout" | "rejected" | "verified" | "unverified";
        /**
         * CommandTargetView
         * @description The outcome of a command for one aircraft.
         */
        CommandTargetView: {
            /** Aircraft Id */
            aircraft_id: string;
            /** Callsign */
            callsign: string | null;
            state: components["schemas"]["CommandTargetState"];
            /** Reason Code */
            reason_code: string | null;
            /** Reason */
            reason: string | null;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /**
         * CommandView
         * @description A command and its per-aircraft outcome.
         */
        CommandView: {
            /** Id */
            id: string;
            kind: components["schemas"]["CommandKind"];
            /** Params */
            params: {
                [key: string]: unknown;
            };
            /** Issued By */
            issued_by: string;
            state: components["schemas"]["CommandState"];
            /** Override */
            override: boolean;
            /** Confirmation Required */
            confirmation_required: boolean;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Confirmed At */
            confirmed_at: string | null;
            /** Completed At */
            completed_at: string | null;
            /** Targets */
            targets: components["schemas"]["CommandTargetView"][];
        };
        /**
         * ConfirmationProblem
         * @description The 428 response body (documented in the OpenAPI document).
         */
        ConfirmationProblem: {
            /** Type */
            type: string;
            /** Title */
            title: string;
            /** Status */
            status: number;
            /** Detail */
            detail?: string | null;
            /** Instance */
            instance?: string | null;
            /** Command Id */
            command_id: string;
            /** Confirmation Token */
            confirmation_token: string;
            /**
             * Expires At
             * Format: date-time
             */
            expires_at: string;
            summary: components["schemas"]["ConfirmationSummary"];
        };
        /**
         * ConfirmationSummary
         * @description What the operator is asked to confirm, computed by the server.
         */
        ConfirmationSummary: {
            kind: components["schemas"]["CommandKind"];
            /** Params */
            params: {
                [key: string]: unknown;
            };
            /** Reasons */
            reasons: string[];
            /** Override */
            override: boolean;
            /** Aircraft */
            aircraft: components["schemas"]["SummaryAircraft"][];
            /** Rejected */
            rejected: components["schemas"]["SummaryRejection"][];
            /**
             * Conflicts
             * @default []
             */
            conflicts: string[];
            /**
             * Preflight
             * @default []
             */
            preflight: string[];
        };
        /**
         * ControlAssignment
         * @description Supervisor: give control to a user (or to nobody), overriding the current holder.
         */
        ControlAssignment: {
            /** User Id */
            user_id: string | null;
            /** Reason */
            reason: string;
        };
        /**
         * DisarmCommand
         * @description Disarm (on the ground only; never in flight).
         */
        DisarmCommand: {
            /**
             * Command Id
             * Format: uuid
             * @description Client-generated; the idempotency key.
             */
            command_id: string;
            /** Aircraft Ids */
            aircraft_ids: string[];
            /**
             * Confirmation Token
             * @description From a 428 answer to this exact request.
             */
            confirmation_token?: string | null;
            /**
             * Kind
             * @constant
             */
            kind: "disarm";
        };
        /**
         * ExportFormat
         * @description Audit export formats.
         * @enum {string}
         */
        ExportFormat: "csv" | "jsonl";
        /**
         * FaultInjection
         * @description Simulation only: inject faults into a simulated aircraft.
         */
        FaultInjection: {
            /**
             * Link
             * @description false: the radio link goes down.
             */
            link?: boolean | null;
            /**
             * Gps
             * @description false: the GNSS fix is lost.
             */
            gps?: boolean | null;
            /** Battery Pct */
            battery_pct?: number | null;
            /**
             * Parameters
             * @description Autopilot parameters to set (the preflight parameters only), e.g. {"NAV_DLL_ACT": 0} for an aircraft that would do nothing on link loss.
             */
            parameters?: {
                [key: string]: number;
            } | null;
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
         * FleetState
         * @description Every registered aircraft's live state.
         */
        FleetState: {
            /** Simulation */
            simulation: boolean;
            /**
             * Server Time
             * Format: date-time
             */
            server_time: string;
            /** Aircraft */
            aircraft: components["schemas"]["AircraftLive"][];
        };
        /**
         * FlightMode
         * @description Autopilot-agnostic flight mode shown to operators (drivers map to it).
         * @enum {string}
         */
        FlightMode: "hold" | "takeoff" | "goto" | "mission" | "return" | "land" | "manual" | "offboard" | "unknown";
        /**
         * Footprint
         * @description The camera, for the lane spacing: 2 · height · tan(HFOV / 2) · (1 - overlap).
         */
        Footprint: {
            /** Hfov Deg */
            hfov_deg: number;
            /** Overlap */
            overlap: number;
            /**
             * Height Agl M
             * @description Height above ground; default: the mission's altitude above home.
             */
            height_agl_m?: number | null;
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
         * GotoCommand
         * @description Fly to a position (and altitude above home), then hold there.
         *
         *     One aircraft flies to the target itself. Several aircraft never share it (ADR 0029):
         *     each gets its own point, ``spread_m`` apart around the target, and its own altitude
         *     layer; their flights are checked in 4D and the command is always confirmed.
         */
        GotoCommand: {
            /**
             * Command Id
             * Format: uuid
             * @description Client-generated; the idempotency key.
             */
            command_id: string;
            /** Aircraft Ids */
            aircraft_ids: string[];
            /**
             * Confirmation Token
             * @description From a 428 answer to this exact request.
             */
            confirmation_token?: string | null;
            /**
             * Kind
             * @constant
             */
            kind: "goto";
            target: components["schemas"]["GeoPoint"];
            /** Altitude Relative M */
            altitude_relative_m?: number | null;
            /**
             * Spread M
             * @description Several aircraft: distance between their points (default: settings).
             */
            spread_m?: number | null;
        };
        /**
         * GpsFix
         * @description GNSS fix quality; MAVLink GPS_FIX_TYPE codes are kept for storage.
         * @enum {string}
         */
        GpsFix: "none" | "2d" | "3d" | "dgps" | "rtk_float" | "rtk_fixed";
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
         * HandoverRequestView
         * @description A pending request to take over control.
         */
        HandoverRequestView: {
            requested_by: components["schemas"]["UserRef"];
            /**
             * Requested At
             * Format: date-time
             */
            requested_at: string;
            /**
             * Expires At
             * Format: date-time
             */
            expires_at: string;
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
         * HoldCommand
         * @description Stop and hold position (hover or loiter). Any operator, any aircraft.
         */
        HoldCommand: {
            /**
             * Command Id
             * Format: uuid
             * @description Client-generated; the idempotency key.
             */
            command_id: string;
            /** Aircraft Ids */
            aircraft_ids: string[];
            /**
             * Confirmation Token
             * @description From a 428 answer to this exact request.
             */
            confirmation_token?: string | null;
            /**
             * Kind
             * @constant
             */
            kind: "hold";
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
         * LandCommand
         * @description Land where the aircraft is.
         */
        LandCommand: {
            /**
             * Command Id
             * Format: uuid
             * @description Client-generated; the idempotency key.
             */
            command_id: string;
            /** Aircraft Ids */
            aircraft_ids: string[];
            /**
             * Confirmation Token
             * @description From a 428 answer to this exact request.
             */
            confirmation_token?: string | null;
            /**
             * Kind
             * @constant
             */
            kind: "land";
        };
        /**
         * LeaseList
         * @description Every control lease.
         */
        LeaseList: {
            /** Items */
            items: components["schemas"]["LeaseView"][];
        };
        /**
         * LeaseState
         * @description Control lease of an aircraft (ADR 0011).
         * @enum {string}
         */
        LeaseState: "held" | "orphaned";
        /**
         * LeaseView
         * @description Who controls an aircraft (ADR 0011).
         */
        LeaseView: {
            /** Aircraft Id */
            aircraft_id: string;
            holder: components["schemas"]["UserRef"];
            state: components["schemas"]["LeaseState"];
            /**
             * Acquired At
             * Format: date-time
             */
            acquired_at: string;
            pending_request: components["schemas"]["HandoverRequestView"] | null;
        };
        /**
         * LinkSource
         * @description The links an aircraft can have (ADR 0025).
         * @enum {string}
         */
        LinkSource: "mavlink" | "swarm";
        /**
         * LinkState
         * @description Freshness of an aircraft's telemetry (ADR 0010).
         * @enum {string}
         */
        LinkState: "live" | "stale" | "lost" | "offline";
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
         * MissionPauseCommand
         * @description Pause the GCS-planned mission the aircraft fly (they hold; resume continues it).
         */
        MissionPauseCommand: {
            /**
             * Command Id
             * Format: uuid
             * @description Client-generated; the idempotency key.
             */
            command_id: string;
            /** Aircraft Ids */
            aircraft_ids: string[];
            /**
             * Confirmation Token
             * @description From a 428 answer to this exact request.
             */
            confirmation_token?: string | null;
            /**
             * Kind
             * @constant
             */
            kind: "mission_pause";
        };
        /**
         * MissionProgressOut
         * @description A mission's progress, with the area swept so far (WGS84 GeoJSON MultiPolygon).
         */
        MissionProgressOut: {
            /** Mission Id */
            mission_id: string;
            /** Incident Id */
            incident_id: string;
            /** Name */
            name: string;
            kind: components["schemas"]["MissionKind"];
            status: components["schemas"]["MissionStatus"];
            /**
             * Coverage
             * @description Share of the search area swept (0-1).
             */
            coverage: number | null;
            /** Tasks */
            tasks: components["schemas"]["TaskProgressView"][];
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /** Coverage Geometry */
            coverage_geometry: {
                [key: string]: unknown;
            } | null;
        };
        /**
         * MissionStartCommand
         * @description Start a planned mission. Always confirmed.
         *
         *     - A swarm area mission (ADR 0024): the swarm protocol cannot address a mission, every
         *       drone on the swarm link adopts it, so ``aircraft_ids`` must be every swarm aircraft,
         *       and exactly the mission's tasks.
         *     - A GCS-planned mission (waypoint, area search; ADR 0028): each aircraft is sent its
         *       own planned route (uploaded, read back, started). Conflicts or clearance issues in
         *       the plan need a supervisor's override.
         */
        MissionStartCommand: {
            /**
             * Command Id
             * Format: uuid
             * @description Client-generated; the idempotency key.
             */
            command_id: string;
            /** Aircraft Ids */
            aircraft_ids: string[];
            /**
             * Confirmation Token
             * @description From a 428 answer to this exact request.
             */
            confirmation_token?: string | null;
            /**
             * Kind
             * @constant
             */
            kind: "mission_start";
            /** Mission Id */
            mission_id: string;
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
         * OperatorPresence
         * @description Someone connected to this station (M5): who, their role, and when last heard.
         */
        OperatorPresence: {
            user: components["schemas"]["UserRef"];
            role: components["schemas"]["Role"];
            /**
             * Last Seen At
             * Format: date-time
             */
            last_seen_at: string;
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
         * PatternKind
         * @description Search patterns (IAMSAR names where they exist).
         * @enum {string}
         */
        PatternKind: "parallel_track" | "creeping_line" | "expanding_square" | "sector" | "contour" | "route";
        /**
         * Permission
         * @description Something a session may be allowed to do.
         * @enum {string}
         */
        Permission: "fleet.view" | "missions.plan" | "alerts.ack" | "aircraft.hold" | "aircraft.command" | "control.override" | "fleet.manage" | "incidents.manage" | "geofences.manage" | "users.view" | "audit.read" | "users.manage";
        /**
         * PlanClearance
         * @description A waypoint too close to the ground or too high.
         */
        PlanClearance: {
            /** Aircraft Id */
            aircraft_id: string;
            /** Callsign */
            callsign: string;
            /** Waypoint */
            waypoint: number;
            /** Kind */
            kind: string;
            /** Height M */
            height_m: number;
        };
        /**
         * PlanConflict
         * @description Two aircraft too close in the plan: where and when they come closest.
         */
        PlanConflict: {
            /** Aircraft Ids */
            aircraft_ids: string[];
            /** Callsigns */
            callsigns: string[];
            /** T S */
            t_s: number;
            /** Latitude */
            latitude: number;
            /** Longitude */
            longitude: number;
            /** Horizontal M */
            horizontal_m: number;
            /** Vertical M */
            vertical_m: number;
        };
        /**
         * PlanOut
         * @description A mission's plan.
         */
        PlanOut: {
            /** Mission Id */
            mission_id: string;
            pattern: components["schemas"]["PatternKind"];
            /** Spacing M */
            spacing_m: number;
            /** Dry Run */
            dry_run: boolean;
            /**
             * Clear
             * @description No conflict and no clearance issue: startable.
             */
            clear: boolean;
            /**
             * Coverage
             * @description Share of the area within the sweep (0-1).
             */
            coverage: number | null;
            /** Area M2 */
            area_m2: number | null;
            /** Duration S */
            duration_s: number;
            /** Tasks */
            tasks: components["schemas"]["PlannedTask"][];
            /** Conflicts */
            conflicts: components["schemas"]["PlanConflict"][];
            /** Clearance */
            clearance: components["schemas"]["PlanClearance"][];
            /** Unchecked Terrain */
            unchecked_terrain: number;
            /** Notes */
            notes: string[];
            /**
             * Planned At
             * Format: date-time
             */
            planned_at: string;
            /** Request */
            request: {
                [key: string]: unknown;
            };
        };
        /**
         * PlanRequest
         * @description What to plan. Area patterns need ``spacing_m`` or ``footprint``; aircraft come from
         *     ``aircraft_ids``, a ``group_id``, or (neither) the mission's current tasks.
         */
        PlanRequest: {
            pattern: components["schemas"]["PatternKind"];
            /** Spacing M */
            spacing_m?: number | null;
            footprint?: components["schemas"]["Footprint"] | null;
            /**
             * Bearing Deg
             * @description Lane direction or first leg, degrees true; default: the area's long axis.
             */
            bearing_deg?: number | null;
            datum?: components["schemas"]["GeoPoint"] | null;
            /** Radius M */
            radius_m?: number | null;
            /**
             * Second Pass
             * @default false
             */
            second_pass: boolean;
            /**
             * Height Agl M
             * @description Contour search: height above the contour lines.
             */
            height_agl_m?: number | null;
            /** Aircraft Ids */
            aircraft_ids?: string[] | null;
            /** Group Id */
            group_id?: string | null;
            /** Overrides */
            overrides?: components["schemas"]["TaskOverride"][];
        };
        /**
         * PlannedTask
         * @description One aircraft's part of a plan.
         */
        PlannedTask: {
            /** Aircraft Id */
            aircraft_id: string;
            /** Callsign */
            callsign: string;
            airframe: components["schemas"]["Airframe"];
            /**
             * Companion
             * @description Has a swarm companion (onboard obstacle avoidance).
             */
            companion: boolean;
            /**
             * Layer M
             * @description Metres added to the planned altitude for separation.
             */
            layer_m: number;
            /** Speed Mps */
            speed_mps: number;
            /** Start Delay S */
            start_delay_s: number;
            /** Strip Area M2 */
            strip_area_m2: number | null;
            /** Length M */
            length_m: number;
            /** Duration S */
            duration_s: number;
            /** Fallback */
            fallback: boolean;
            /** Infeasible Turns */
            infeasible_turns: number;
            /** Notes */
            notes: string[];
            /** Waypoints */
            waypoints: components["schemas"]["PlannedWaypoint"][];
        };
        /**
         * PlannedWaypoint
         * @description One waypoint of a planned route (altitude above the aircraft's home).
         */
        PlannedWaypoint: {
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
         * PoiCreate
         * @description A point an operator marks.
         */
        PoiCreate: {
            /** @default poi */
            kind: components["schemas"]["PoiKind"];
            position: components["schemas"]["GeoPoint"];
            /** Uncertainty M */
            uncertainty_m?: number | null;
            /** Notes */
            notes?: string | null;
        };
        /**
         * PoiKind
         * @description A point of interest: a place operators mark, or a survivor sighting a drone reports.
         * @enum {string}
         */
        PoiKind: "poi" | "survivor_sighting" | "clue" | "hazard";
        /**
         * PoiPage
         * @description A page of points of interest.
         */
        PoiPage: {
            /** Items */
            items: components["schemas"]["PoiView"][];
            /**
             * Next Cursor
             * @description Null when this is the last page.
             */
            next_cursor: string | null;
        };
        /**
         * PoiStatus
         * @description What operators made of a point of interest.
         * @enum {string}
         */
        PoiStatus: "new" | "confirmed" | "dismissed" | "resolved";
        /**
         * PoiUpdate
         * @description What operators decide about a point, or add to it.
         */
        PoiUpdate: {
            kind?: components["schemas"]["PoiKind"];
            status?: components["schemas"]["PoiStatus"];
            /** Notes */
            notes?: string | null;
        };
        /**
         * PoiView
         * @description A point of interest: marked by an operator, or a survivor sighting a drone reported.
         */
        PoiView: {
            /** Id */
            id: string;
            /** Incident Id */
            incident_id: string;
            kind: components["schemas"]["PoiKind"];
            status: components["schemas"]["PoiStatus"];
            /** Latitude */
            latitude: number;
            /** Longitude */
            longitude: number;
            /**
             * Uncertainty M
             * @description 1-sigma horizontal uncertainty [m].
             */
            uncertainty_m: number | null;
            /**
             * Aircraft Id
             * @description The reporting aircraft (null: an operator).
             */
            aircraft_id: string | null;
            /** Reported At */
            reported_at: string | null;
            /** Notes */
            notes: string | null;
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
         * PreflightFindingView
         * @description One problem with an aircraft's failsafe configuration.
         */
        PreflightFindingView: {
            /** Parameter */
            parameter: string;
            /** Value */
            value: number | null;
            /**
             * Severity
             * @description block: arm and takeoff are refused (a supervisor may override); warn: shown.
             * @enum {string}
             */
            severity: "block" | "warn";
            /** Message */
            message: string;
        };
        /**
         * PreflightReportView
         * @description An aircraft's failsafe parameters and the station's findings (M6, ADR 0035).
         */
        PreflightReportView: {
            /** Aircraft Id */
            aircraft_id: string;
            /**
             * Checked At
             * @description None: never checked.
             */
            checked_at: string | null;
            /**
             * Values
             * @description None: could not be read.
             */
            values: {
                [key: string]: number | null;
            };
            /** Findings */
            findings: components["schemas"]["PreflightFindingView"][];
            /**
             * Ready
             * @description Checked, and nothing blocks arm and takeoff.
             */
            ready: boolean;
        };
        /**
         * PresenceList
         * @description The users heard in the last 30 seconds, most recently heard first.
         */
        PresenceList: {
            /** Users */
            users: components["schemas"]["OperatorPresence"][];
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
         * ResumeCommand
         * @description Continue what HOLD paused.
         */
        ResumeCommand: {
            /**
             * Command Id
             * Format: uuid
             * @description Client-generated; the idempotency key.
             */
            command_id: string;
            /** Aircraft Ids */
            aircraft_ids: string[];
            /**
             * Confirmation Token
             * @description From a 428 answer to this exact request.
             */
            confirmation_token?: string | null;
            /**
             * Kind
             * @constant
             */
            kind: "resume";
        };
        /**
         * ReturnCommand
         * @description Return to launch and land.
         */
        ReturnCommand: {
            /**
             * Command Id
             * Format: uuid
             * @description Client-generated; the idempotency key.
             */
            command_id: string;
            /** Aircraft Ids */
            aircraft_ids: string[];
            /**
             * Confirmation Token
             * @description From a 428 answer to this exact request.
             */
            confirmation_token?: string | null;
            /**
             * Kind
             * @constant
             */
            kind: "return_to_launch";
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
         * StreamHealthList
         * @description Every registered stream's health; ``monitored`` is false without a relay API.
         */
        StreamHealthList: {
            /** Monitored */
            monitored: boolean;
            /** Streams */
            streams: components["schemas"]["StreamHealthOut"][];
        };
        /**
         * StreamHealthOut
         * @description How a stream is doing at the relay; ``unknown`` when the relay cannot be asked.
         */
        StreamHealthOut: {
            /** Stream Id */
            stream_id: string;
            /** Relay Path */
            relay_path: string;
            state: components["schemas"]["StreamState"];
            /** Since */
            since: string | null;
            /** Readers */
            readers: number | null;
            /** Bitrate Kbps */
            bitrate_kbps: number | null;
            /** Checked At */
            checked_at: string | null;
        };
        /**
         * StreamState
         * @description Whether video is flowing through the relay.
         * @enum {string}
         */
        StreamState: "live" | "stalled" | "offline" | "unknown";
        /**
         * SummaryAircraft
         * @description An aircraft the command would be sent to, with what the operator should notice.
         */
        SummaryAircraft: {
            /** Aircraft Id */
            aircraft_id: string;
            /** Callsign */
            callsign: string;
            /** Warnings */
            warnings: string[];
            target?: components["schemas"]["GeoPoint"] | null;
            /** Altitude Relative M */
            altitude_relative_m?: number | null;
            /** Start Delay S */
            start_delay_s?: number | null;
        };
        /**
         * SummaryRejection
         * @description An aircraft the command will not be sent to, and why.
         */
        SummaryRejection: {
            /** Aircraft Id */
            aircraft_id: string;
            /** Callsign */
            callsign: string | null;
            /** Code */
            code: string;
            /** Message */
            message: string;
        };
        /**
         * SurvivorSightingView
         * @description Where a swarm drone's estimate puts a person (the onboard "target" estimate).
         */
        SurvivorSightingView: {
            position: components["schemas"]["GeoPoint"];
            /**
             * Std M
             * @description 1-sigma horizontal uncertainty [m].
             */
            std_m: number;
            /**
             * Stamp
             * Format: date-time
             */
            stamp: string;
        };
        /**
         * SwarmFault
         * @description Bits of the onboard ``DroneState.faults``, by name.
         * @enum {string}
         */
        SwarmFault: "fc_link" | "pose_stale" | "pose_invalid" | "attitude_stale" | "no_global_reference" | "depth_stale" | "depth_blind" | "outside_geofence" | "altitude_mismatch" | "waypoint_unreachable" | "mission_rejected" | "control_overrun" | "radio_silent";
        /**
         * SwarmHealth
         * @description A swarm companion's own health verdict (onboard ``DroneState.HEALTH_*``).
         * @enum {string}
         */
        SwarmHealth: "ok" | "degraded" | "critical";
        /**
         * SwarmPhase
         * @description What a swarm companion is doing (onboard ``DroneState.PHASE_*``, ADR 0003).
         * @enum {string}
         */
        SwarmPhase: "standby" | "transit" | "search" | "track" | "hold";
        /**
         * SwarmView
         * @description What an aircraft's swarm companion reports (ADR 0003).
         */
        SwarmView: {
            /** Drone Id */
            drone_id: number;
            phase: components["schemas"]["SwarmPhase"];
            health: components["schemas"]["SwarmHealth"];
            /** Faults */
            faults: components["schemas"]["SwarmFault"][];
            /**
             * Mission Sequence
             * @description Active swarm mission (0: none).
             */
            mission_sequence: number;
            /**
             * Command Sequence
             * @description Last operator command the drone processed.
             */
            command_sequence: number;
            /**
             * Nearest Obstacle M
             * @description Null: no obstacle known.
             */
            nearest_obstacle_m: number | null;
            survivor_sighting: components["schemas"]["SurvivorSightingView"] | null;
        };
        /**
         * TakeoffCommand
         * @description Take off to an altitude above home. Always confirmed.
         */
        TakeoffCommand: {
            /**
             * Command Id
             * Format: uuid
             * @description Client-generated; the idempotency key.
             */
            command_id: string;
            /** Aircraft Ids */
            aircraft_ids: string[];
            /**
             * Confirmation Token
             * @description From a 428 answer to this exact request.
             */
            confirmation_token?: string | null;
            /**
             * Kind
             * @constant
             */
            kind: "takeoff";
            /**
             * Altitude Relative M
             * @description Metres above home.
             */
            altitude_relative_m: number;
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
         * TaskOverride
         * @description Per-aircraft changes to the mission's defaults.
         */
        TaskOverride: {
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
         * TaskProgressView
         * @description How far one aircraft is through its part of a mission.
         */
        TaskProgressView: {
            /** Task Id */
            task_id: string;
            /** Aircraft Id */
            aircraft_id: string;
            /** Callsign */
            callsign: string;
            status: components["schemas"]["TaskStatus"];
            /**
             * Item
             * @description Waypoint being flown (0-based). Null: unknown.
             */
            item: number | null;
            /**
             * Items
             * @description Waypoints of its route. Null: unknown.
             */
            items: number | null;
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
         * TelemetryHistory
         * @description Recorded telemetry of one aircraft, oldest first.
         */
        TelemetryHistory: {
            /** Aircraft Id */
            aircraft_id: string;
            /** Samples */
            samples: components["schemas"]["TelemetryPoint"][];
            /**
             * Truncated
             * @description True if more samples match than ``limit`` allowed.
             */
            truncated: boolean;
        };
        /**
         * TelemetryPoint
         * @description One recorded telemetry sample (downsampled history, ADR 0007).
         */
        TelemetryPoint: {
            /**
             * Ts
             * Format: date-time
             */
            ts: string;
            position: components["schemas"]["GeoPoint"] | null;
            /** Altitude Amsl M */
            altitude_amsl_m: number | null;
            /** Altitude Relative M */
            altitude_relative_m: number | null;
            /** Heading Deg */
            heading_deg: number | null;
            /** Groundspeed Mps */
            groundspeed_mps: number | null;
            /** Climb Rate Mps */
            climb_rate_mps: number | null;
            /** Battery Pct */
            battery_pct: number | null;
            gps_fix: components["schemas"]["GpsFix"] | null;
            flight_mode: components["schemas"]["FlightMode"] | null;
            /** Armed */
            armed: boolean | null;
            /** In Air */
            in_air: boolean | null;
        };
        /**
         * TelemetryView
         * @description The latest telemetry of an aircraft; unknown values are null (ADR 0002, S7).
         */
        TelemetryView: {
            /**
             * Ts
             * Format: date-time
             */
            ts: string;
            /** Source */
            source: string;
            position: components["schemas"]["GeoPoint"] | null;
            /** Altitude Amsl M */
            altitude_amsl_m: number | null;
            /** Altitude Relative M */
            altitude_relative_m: number | null;
            /** Heading Deg */
            heading_deg: number | null;
            /** Groundspeed Mps */
            groundspeed_mps: number | null;
            /** Climb Rate Mps */
            climb_rate_mps: number | null;
            /** Battery Pct */
            battery_pct: number | null;
            /** Battery V */
            battery_v: number | null;
            /** @description Null: the link does not report GNSS quality. */
            gps_fix: components["schemas"]["GpsFix"] | null;
            /** Satellites */
            satellites: number | null;
            flight_mode: components["schemas"]["FlightMode"];
            /** Armed */
            armed: boolean | null;
            /** In Air */
            in_air: boolean | null;
            home: components["schemas"]["GeoPoint"] | null;
            /** @description Only for aircraft with a swarm link. */
            swarm: components["schemas"]["SwarmView"] | null;
            /**
             * Mission Item
             * @description Mission item flown (0-based); equals mission_items once done. Null: none.
             */
            mission_item?: number | null;
            /**
             * Mission Items
             * @description Items of the loaded mission.
             */
            mission_items?: number | null;
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
         * UserRef
         * @description A user, as shown next to what they do.
         */
        UserRef: {
            /** User Id */
            user_id: string;
            /** Username */
            username: string;
            /** Display Name */
            display_name: string;
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
            /** Simulation */
            simulation: boolean;
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
         * ViewTicket
         * @description Where a console plays a stream: WHEP (WebRTC) first, LL-HLS if WebRTC fails.
         */
        ViewTicket: {
            /** Stream Id */
            stream_id: string;
            /** Name */
            name: string;
            /** Whep Url */
            whep_url: string;
            /** Hls Url */
            hls_url: string;
            /**
             * Ticket
             * @description Send as `Authorization: Bearer <ticket>` with every WHEP and HLS request; the relay asks the fleet service (M6, ADR 0036).
             */
            ticket: string;
            /**
             * Expires At
             * Format: date-time
             * @description Ask again after this.
             */
            expires_at: string;
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
    export_incident_api_v1_incidents__incident_id__export_get: {
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
            /** @description The bundle. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/zip": unknown;
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
    get_plan_api_v1_missions__mission_id__plan_get: {
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
                    "application/json": components["schemas"]["PlanOut"];
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
    plan_api_v1_missions__mission_id__plan_post: {
        parameters: {
            query?: {
                /** @description Only compute and answer; save nothing. */
                dry_run?: boolean;
            };
            header?: never;
            path: {
                mission_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PlanRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PlanOut"];
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
    get_progress_api_v1_missions__mission_id__progress_get: {
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
                    "application/json": components["schemas"]["MissionProgressOut"];
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
    list_pois_api_v1_incidents__incident_id__pois_get: {
        parameters: {
            query?: {
                status?: components["schemas"]["PoiStatus"] | null;
                /** @description Maximum items to return. */
                limit?: number;
                /** @description Opaque cursor from a previous page's next_cursor. */
                cursor?: string | null;
            };
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
                    "application/json": components["schemas"]["PoiPage"];
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
    create_poi_api_v1_incidents__incident_id__pois_post: {
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
                "application/json": components["schemas"]["PoiCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PoiView"];
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
    get_poi_api_v1_pois__poi_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                poi_id: string;
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
                    "application/json": components["schemas"]["PoiView"];
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
    update_poi_api_v1_pois__poi_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                poi_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PoiUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PoiView"];
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
    view_video_stream_api_v1_video_streams__stream_id__view_post: {
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
                    "application/json": components["schemas"]["ViewTicket"];
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
    video_health_api_v1_video_health_get: {
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
                    "application/json": components["schemas"]["StreamHealthList"];
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
    list_presence_api_v1_presence_get: {
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
                    "application/json": components["schemas"]["PresenceList"];
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
    fleet_state_api_v1_fleet_state_get: {
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
                    "application/json": components["schemas"]["FleetState"];
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
    telemetry_history_api_v1_aircraft__aircraft_id__telemetry_get: {
        parameters: {
            query?: {
                since?: string | null;
                until?: string | null;
                limit?: number;
            };
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
                    "application/json": components["schemas"]["TelemetryHistory"];
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
    preflight_report_api_v1_aircraft__aircraft_id__preflight_get: {
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
                    "application/json": components["schemas"]["PreflightReportView"];
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
    run_preflight_api_v1_aircraft__aircraft_id__preflight_post: {
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
                    "application/json": components["schemas"]["PreflightReportView"];
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
    inject_fault_api_v1_simulation_aircraft__aircraft_id__faults_post: {
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
                "application/json": components["schemas"]["FaultInjection"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AircraftLive"];
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
    list_commands_api_v1_commands_get: {
        parameters: {
            query?: {
                limit?: number;
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
                    "application/json": components["schemas"]["CommandList"];
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
    submit_command_api_v1_commands_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ArmCommand"] | components["schemas"]["DisarmCommand"] | components["schemas"]["TakeoffCommand"] | components["schemas"]["HoldCommand"] | components["schemas"]["ResumeCommand"] | components["schemas"]["ReturnCommand"] | components["schemas"]["LandCommand"] | components["schemas"]["GotoCommand"] | components["schemas"]["MissionStartCommand"] | components["schemas"]["MissionPauseCommand"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CommandView"];
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
            /** @description Confirmation required: re-send the same request with the token. */
            428: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ConfirmationProblem"];
                };
            };
        };
    };
    get_command_api_v1_commands__command_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                command_id: string;
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
                    "application/json": components["schemas"]["CommandView"];
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
    list_leases_api_v1_control_leases_get: {
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
                    "application/json": components["schemas"]["LeaseList"];
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
    assign_control_api_v1_aircraft__aircraft_id__control_put: {
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
                "application/json": components["schemas"]["ControlAssignment"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LeaseView"] | null;
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
    take_control_api_v1_aircraft__aircraft_id__control_post: {
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
                    "application/json": components["schemas"]["LeaseView"];
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
    release_control_api_v1_aircraft__aircraft_id__control_delete: {
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
    request_handover_api_v1_aircraft__aircraft_id__control_handover_post: {
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
                    "application/json": components["schemas"]["LeaseView"];
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
    accept_handover_api_v1_aircraft__aircraft_id__control_handover_accept_post: {
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
                    "application/json": components["schemas"]["LeaseView"];
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
    decline_handover_api_v1_aircraft__aircraft_id__control_handover_decline_post: {
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
                    "application/json": components["schemas"]["LeaseView"];
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
    list_alerts_api_v1_alerts_get: {
        parameters: {
            query?: {
                state?: components["schemas"]["AlertState"] | null;
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
                    "application/json": components["schemas"]["AlertPage"];
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
    acknowledge_alert_api_v1_alerts__alert_id__acknowledge_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                alert_id: string;
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
                    "application/json": components["schemas"]["AlertView"];
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
                /** @description Maximum items to return. */
                limit?: number;
                /** @description Opaque cursor from a previous page's next_cursor. */
                cursor?: string | null;
                actor_user_id?: string | null;
                /** @description Prefix, e.g. 'auth.' or 'mission.update'. */
                action?: string | null;
                entity_type?: string | null;
                entity_id?: string | null;
                since?: string | null;
                until?: string | null;
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
    verify_audit_chain_api_v1_audit_verify_get: {
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
                    "application/json": components["schemas"]["ChainStatus"];
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
    export_audit_events_api_v1_audit_export_get: {
        parameters: {
            query?: {
                format?: components["schemas"]["ExportFormat"];
                actor_user_id?: string | null;
                /** @description Prefix, e.g. 'auth.' or 'mission.update'. */
                action?: string | null;
                entity_type?: string | null;
                entity_id?: string | null;
                since?: string | null;
                until?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description The selected events, oldest first, with their chain hashes. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "text/csv": string;
                    "application/x-ndjson": string;
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
