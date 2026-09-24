import { getAccessToken, getStoredUser } from "./storage";


it("migrates an existing SupportAI session to AiderAI storage keys", () => {
  sessionStorage.setItem("supportai.access_token", "legacy-token");
  sessionStorage.setItem(
    "supportai.user",
    JSON.stringify({ id: "user-1", email: "person@example.com" }),
  );

  expect(getAccessToken()).toBe("legacy-token");
  expect(getStoredUser<{ id: string }>()).toEqual({
    id: "user-1",
    email: "person@example.com",
  });
  expect(sessionStorage.getItem("aiderai.access_token")).toBe("legacy-token");
  expect(sessionStorage.getItem("aiderai.user")).toContain("person@example.com");
  expect(sessionStorage.getItem("supportai.access_token")).toBeNull();
  expect(sessionStorage.getItem("supportai.user")).toBeNull();
});


it("updates the legacy demo email while migrating the stored user", () => {
  sessionStorage.setItem(
    "supportai.user",
    JSON.stringify({ id: "demo-user", email: "demo@supportai.local", name: "Demo User" }),
  );

  expect(getStoredUser<{ email: string }>()).toMatchObject({
    email: "demo@aiderai.local",
  });
  expect(sessionStorage.getItem("aiderai.user")).toContain("demo@aiderai.local");
  expect(sessionStorage.getItem("aiderai.user")).not.toContain("demo@supportai.local");
});
