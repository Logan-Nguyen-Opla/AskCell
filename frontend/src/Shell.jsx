import { useState } from "react";
import Home from "./Home.jsx";
import FlowApp from "./FlowApp.jsx";

/**
 * Shell
 * -----
 * Simple two-screen switch: the Home explainer first, then the actual tool
 * once "Launch" is clicked. No router -- one boolean is all this needs.
 */
export default function Shell() {
  const [launched, setLaunched] = useState(false);
  return launched ? <FlowApp /> : <Home onLaunch={() => setLaunched(true)} />;
}
