// Shared workout constants: idea library, blogger links, training-focus options.

export const WHAT_OPTIONS = [
  { value: "upper_body", key: "wt_upper", labelEn: "Upper body" },
  { value: "lower_body", key: "wt_lower", labelEn: "Lower body" },
  { value: "push", key: "wt_push", labelEn: "Push" },
  { value: "pull", key: "wt_pull", labelEn: "Pull" },
  { value: "legs", key: "wt_legs", labelEn: "Legs" },
  { value: "full_body", key: "wt_full", labelEn: "Full body" },
  { value: "conditioning", key: "wt_conditioning", labelEn: "Conditioning" },
];

// Where to train — selectable list.
export const WHERE_OPTIONS = [
  { value: "commercial_gym", key: "wl_commercial", labelEn: "Commercial gym" },
  { value: "home", key: "wl_home", labelEn: "At home" },
  { value: "outdoor", key: "wl_outdoor", labelEn: "Outdoors" },
  { value: "hotel_gym", key: "wl_hotel", labelEn: "Hotel gym" },
];

// Load level — Light / Moderate (recommended) / Heavy.
export const INTENSITY_OPTIONS = [
  { value: "light", key: "workout_light" },
  { value: "moderate", key: "workout_moderate", recommended: true },
  { value: "heavy", key: "workout_heavy" },
];

// Map training focus to WorkoutLog.workout_type enum.
export const WHAT_TO_WORKOUT_TYPE = {
  upper_body: "upper_body",
  lower_body: "lower_body",
  push: "upper_body",
  pull: "upper_body",
  legs: "lower_body",
  full_body: "full_body",
  conditioning: "crossfit",
};

export const HOME_WORKOUTS = [
  { name: "Home Full Body", exercises: ["Push-ups — 3×12", "Bodyweight Squats — 3×15", "Lunges — 3×12/leg", "Plank — 3×45s", "Glute Bridge — 3×15"] },
  { name: "Home Core", exercises: ["Crunches — 3×20", "Leg Raises — 3×15", "Plank — 3×60s", "Russian Twists — 3×20"] },
  { name: "Home HIIT", exercises: ["Jumping Jacks — 40s", "Burpees — 30s", "Mountain Climbers — 40s", "Squat Jumps — 30s (4 rounds)"] },
];

export const OUTDOOR_WORKOUTS = [
  { name: "Park Run", exercises: ["5 km easy run", "6×30s strides", "5 min walk cool-down"] },
  { name: "Stairs & Hills", exercises: ["Stair climbs — 5 rounds", "Hill sprints — 6×20s", "Walk down to recover"] },
  { name: "Outdoor Calisthenics", exercises: ["Pull-ups — 4×6", "Bench Dips — 3×10", "Hanging Leg Raises — 3×10", "Push-ups — 3×15"] },
];

export const BLOGGERS = [
  {
    name: "Calisthenics with Ekaterina",
    noteKey: "blog_ekaterina",
    links: [
      { platform: "Telegram", handle: "@FORMre", url: "https://t.me/FORMre" },
      { platform: "YouTube", handle: "@REFORMFORM", url: "https://www.youtube.com/@REFORMFORM" },
    ],
  },
];