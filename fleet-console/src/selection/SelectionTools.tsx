// Ways to select aircraft besides clicking: box, lasso, the list's filter, a group, all.
import type { GroupOut } from '../api/types';
import { useLive } from '../live/store';
import { type Tool, useSelection } from './store';

interface Props {
  groups: GroupOut[];
  filteredIds: string[];
}

export function SelectionTools({ groups, filteredIds }: Props) {
  const tool = useSelection((s) => s.tool);
  const setTool = useSelection((s) => s.setTool);
  const select = useSelection((s) => s.select);
  const clear = useSelection((s) => s.clear);

  const toolButton = (value: Tool, label: string, key: string) => (
    <button
      type="button"
      aria-pressed={tool === value}
      title={`${label} (${key})`}
      onClick={() => {
        setTool(tool === value ? 'pan' : value);
      }}
    >
      {label}
    </button>
  );

  return (
    <div className="selection-tools" role="toolbar" aria-label="Selection">
      {toolButton('box', 'Box', 'B')}
      {toolButton('lasso', 'Lasso', 'L')}
      <button
        type="button"
        title="Select all (Ctrl+A)"
        onClick={() => {
          select(Object.keys(useLive.getState().aircraft));
        }}
      >
        All
      </button>
      <button
        type="button"
        title="Select the aircraft the list shows"
        onClick={() => {
          select(filteredIds);
        }}
      >
        Filtered
      </button>
      <select
        aria-label="Select a group"
        value=""
        onChange={(e) => {
          const group = groups.find((g) => g.id === e.target.value);
          if (group) select(group.aircraft_ids);
        }}
      >
        <option value="">Group…</option>
        {groups.map((g) => (
          <option key={g.id} value={g.id}>
            {g.name} ({g.aircraft_ids.length})
          </option>
        ))}
      </select>
      <button type="button" title="Clear the selection (Esc)" onClick={clear}>
        Clear
      </button>
    </div>
  );
}
