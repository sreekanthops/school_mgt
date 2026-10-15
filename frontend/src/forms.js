import { GRADES, gradeLabel } from "./api.js";

export const SECTIONS = ["A", "B", "C", "D"];

export const studentFields = [
  { key: "name", label: "Full name", required: true },
  { key: "gender", label: "Gender", type: "select", options: ["Male", "Female", "Other"], default: "Male" },
  { key: "dob", label: "Date of birth", type: "date", required: true },
  { key: "grade", label: "Class", type: "select", options: GRADES.map((g) => [g, gradeLabel(g)]), default: "1" },
  { key: "section", label: "Section", type: "select", options: SECTIONS, default: "A" },
  { key: "guardian_name", label: "Guardian name", required: true },
  { key: "phone", label: "Phone", required: true },
  { key: "email", label: "Email", type: "email" },
  { key: "blood_group", label: "Blood group", type: "select", options: ["", "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"] },
  { key: "address", label: "Address", full: true },
];

export const staffFields = [
  { key: "name", label: "Full name", required: true },
  { key: "gender", label: "Gender", type: "select", options: ["Male", "Female", "Other"], default: "Female" },
  { key: "designation", label: "Designation", required: true },
  { key: "department", label: "Department", required: true },
  { key: "qualification", label: "Qualification", required: true },
  { key: "experience_years", label: "Experience (years)", type: "number", min: 0, max: 60, required: true, default: 0 },
  { key: "subjects", label: "Subjects taught (comma separated)" },
  { key: "class_teacher_of", label: "Class teacher of (e.g. 5-A)" },
  { key: "phone", label: "Phone", required: true },
  { key: "email", label: "Email", type: "email", required: true },
  { key: "joined_on", label: "Joined on", type: "date", required: true },
  { key: "bio", label: "About", type: "textarea", full: true },
];

export const schoolFields = [
  { key: "name", label: "School name", required: true, full: true },
  { key: "city", label: "City" },
  { key: "state", label: "State" },
  { key: "board", label: "Board", type: "select", options: ["", "CBSE", "ICSE", "State Board", "IB", "Cambridge (IGCSE)", "Other"] },
  { key: "school_type", label: "Type", type: "select", options: ["", "Co-educational", "Boys", "Girls"] },
  { key: "founded", label: "Founded (year)" },
  { key: "email", label: "Email", type: "email" },
  { key: "phone", label: "Phone" },
  { key: "website", label: "Website (https://…)" },
  { key: "address", label: "Address", full: true },
  { key: "plan", label: "Plan", type: "select", options: ["Free", "Standard", "Premium"], default: "Standard" },
  { key: "max_students", label: "Student limit", type: "number", min: 1, max: 1000000, default: 1000 },
  { key: "max_staff", label: "Staff limit", type: "number", min: 1, max: 100000, default: 100 },
  { key: "subscription_end", label: "Subscription ends", type: "date" },
  { key: "notes", label: "Private notes (platform team only)", type: "textarea", full: true },
];

export const branchFields = [
  { key: "name", label: "Branch name", required: true, full: true },
  { key: "city", label: "City" },
  { key: "principal", label: "Branch principal" },
  { key: "phone", label: "Phone" },
  { key: "email", label: "Email", type: "email" },
  { key: "address", label: "Address", full: true },
];
