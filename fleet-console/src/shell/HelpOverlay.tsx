import * as Dialog from '@radix-ui/react-dialog';

import { SHORTCUTS } from './shortcuts';

export function HelpOverlay({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Dialog.Root
      open={open}
      onOpenChange={(value) => {
        if (!value) onClose();
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="dialog">
          <Dialog.Title>Keyboard shortcuts</Dialog.Title>
          <Dialog.Description>
            Risky commands (arm, takeoff, return, land, goto) have no shortcut and always need a
            held confirmation.
          </Dialog.Description>
          <table className="shortcuts">
            <tbody>
              {SHORTCUTS.map((s) => (
                <tr key={s.keys}>
                  <th scope="row">
                    <kbd>{s.keys}</kbd>
                  </th>
                  <td>{s.action}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="dialog-actions">
            <Dialog.Close asChild>
              <button type="button">Close</button>
            </Dialog.Close>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
