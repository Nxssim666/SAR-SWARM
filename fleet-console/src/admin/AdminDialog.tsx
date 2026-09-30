// Station administration (M5), for supervisors and admins: users, the aircraft registry
// (M6) and the audit trail.
import * as Dialog from '@radix-ui/react-dialog';
import { useState } from 'react';

import { can, useSession } from '../session/session';
import { AircraftPanel } from './AircraftPanel';
import { AuditPanel } from './AuditPanel';
import { UsersPanel } from './UsersPanel';

type Tab = 'users' | 'aircraft' | 'audit';

export function AdminButton() {
  const session = useSession((s) => s.session);
  const [open, setOpen] = useState(false);
  const users = can(session, 'users.view');
  const fleet = can(session, 'fleet.manage');
  const audit = can(session, 'audit.read');
  const [tab, setTab] = useState<Tab>(users ? 'users' : fleet ? 'aircraft' : 'audit');
  if (!users && !fleet && !audit) return null;

  return (
    <>
      <button
        type="button"
        onClick={() => {
          setOpen(true);
        }}
      >
        Admin
      </button>
      {open && (
        <Dialog.Root
          open
          onOpenChange={(value) => {
            if (!value) setOpen(false);
          }}
        >
          <Dialog.Portal>
            <Dialog.Overlay className="dialog-overlay" />
            <Dialog.Content className="dialog dialog-wide">
              <div className="row spread">
                <Dialog.Title>Administration</Dialog.Title>
                <Dialog.Close asChild>
                  <button type="button">Close</button>
                </Dialog.Close>
              </div>
              <Dialog.Description className="muted">
                Everything done here is audited.
              </Dialog.Description>
              <div className="tabs" role="tablist" aria-label="Administration">
                {users && (
                  <button
                    type="button"
                    role="tab"
                    aria-selected={tab === 'users'}
                    onClick={() => {
                      setTab('users');
                    }}
                  >
                    Users
                  </button>
                )}
                {fleet && (
                  <button
                    type="button"
                    role="tab"
                    aria-selected={tab === 'aircraft'}
                    onClick={() => {
                      setTab('aircraft');
                    }}
                  >
                    Aircraft
                  </button>
                )}
                {audit && (
                  <button
                    type="button"
                    role="tab"
                    aria-selected={tab === 'audit'}
                    onClick={() => {
                      setTab('audit');
                    }}
                  >
                    Audit
                  </button>
                )}
              </div>
              <div role="tabpanel">
                {tab === 'users' && users && <UsersPanel />}
                {tab === 'aircraft' && fleet && <AircraftPanel />}
                {tab === 'audit' && audit && <AuditPanel />}
              </div>
            </Dialog.Content>
          </Dialog.Portal>
        </Dialog.Root>
      )}
    </>
  );
}
