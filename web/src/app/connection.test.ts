import { describe, expect, it } from "vitest";
import { windowParams, windowUrl } from "./connection";

describe("window parameters (M6 slice S3)", () => {
  it("reads the session and role from the URL", () => {
    expect(windowParams("?session=abc123&role=operator")).toEqual({ session: "abc123", role: "operator", fresh: false });
    expect(windowParams("?session=abc&role=instructor").role).toBe("instructor");
  });

  it("defaults to role full, and makes a new session id when there is none or it is not valid", () => {
    expect(windowParams("", () => "new1")).toEqual({ session: "new1", role: "full", fresh: true });
    expect(windowParams("?session=../x&role=boss", () => "new2")).toEqual({ session: "new2", role: "full", fresh: true });
    expect(windowParams(`?session=${"a".repeat(41)}`, () => "new3").session).toBe("new3");
  });

  it("builds the URL of another window of the same session", () => {
    const u = new URL(windowUrl("https://example.org/app/?session=old&role=full#x", "s1", "operator"));
    expect(u.pathname).toBe("/app/");
    expect([u.searchParams.get("session"), u.searchParams.get("role"), u.hash]).toEqual(["s1", "operator", ""]);
  });
});
