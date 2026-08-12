function o({sessionId:t,projectId:n}){const e=new URLSearchParams({session_id:t});return n&&e.set("project_id",n),`agentmate://open/run?${e.toString()}`}export{o as d};
