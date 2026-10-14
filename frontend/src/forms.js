import { GRADES, gradeLabel } from "./api.js";

export const SECTIONS = ["A", "B", "C", "D"];

export const studentFields = [
  { key: "admission_no", label: "Admission no.", required: true },
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
  { key: "employee_id", label: "Employee ID", required: true },
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
