export interface Notif {
  id: number;
  user_id: string | null;
  kind: string;
  run_id: string | null;
  message: string;
  read_at: string | null;
  created_at: string;
}

export type NotifAction =
  | { type: "set"; items: Notif[] }
  | { type: "add"; item: Notif }
  | { type: "read"; id: number; at: string };

export function notificationsReducer(state: Notif[], action: NotifAction): Notif[] {
  switch (action.type) {
    case "set":
      return action.items;
    case "add":
      if (state.some((n) => n.id === action.item.id)) return state;
      return [action.item, ...state];
    case "read":
      return state.map((n) => (n.id === action.id && !n.read_at ? { ...n, read_at: action.at } : n));
  }
}

export const unreadCount = (state: Notif[]): number => state.filter((n) => !n.read_at).length;
