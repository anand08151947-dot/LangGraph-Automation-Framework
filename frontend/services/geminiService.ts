
import { GoogleGenAI } from "@google/genai";

const ai = new GoogleGenAI({ apiKey: process.env.API_KEY || '' });

export const translateEnglishToJSON = async (instruction: string): Promise<string> => {
  if (!process.env.API_KEY) return '{"error": "API Key not found"}';
  
  try {
    const response = await ai.models.generateContent({
      model: 'gemini-3-flash-preview',
      contents: `Translate the following description of an AI agentic workflow into a structured JSON configuration. 
      The JSON should include "agents" (with name, role, tools), "workflow_logic" (steps, transitions), and "environment_config".
      
      Description: "${instruction}"`,
      config: {
        responseMimeType: "application/json",
      }
    });
    
    return response.text || "{}";
  } catch (error) {
    console.error("Gemini Translation Error:", error);
    return JSON.stringify({ error: "Failed to translate instructions" }, null, 2);
  }
};

export const refineWorkflowJSON = async (currentJson: string, instruction: string): Promise<string> => {
  if (!process.env.API_KEY) return currentJson;

  try {
    const response = await ai.models.generateContent({
      model: 'gemini-3-flash-preview',
      contents: `You are an expert at agentic systems. Refine the following JSON workflow based on these additional instructions.
      
      Current JSON:
      ${currentJson}
      
      Refinement Instructions:
      "${instruction}"`,
      config: {
        responseMimeType: "application/json",
      }
    });
    
    return response.text || currentJson;
  } catch (error) {
    console.error("Gemini Refinement Error:", error);
    return currentJson;
  }
};
