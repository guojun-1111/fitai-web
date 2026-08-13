// Shared mutable state between modules
export const state = {
  ws: null,
  wsConnected: false,
  thinking: false,
  activeReq: null,
  reconnectDelay: 1000,
  pendingMessages: [],
  speakEnabled: false,
  callActive: false,
  _homeDataLoaded: false,
  _lastHomeData: null,
};
