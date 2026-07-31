import React, { useRef, useEffect } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import AnimatedOutlet from "@/components/AnimatedOutlet";
import LanguageSwitcher from "@/components/LanguageSwitcher";
import { useLang } from "@/lib/i18n";
import { ChevronLeft, LayoutDashboard, Sparkles, MessageSquare, ShoppingCart, User, Dumbbell } from "lucide-react";

const navItems = [
  { path: "/", icon: LayoutDashboard, labelKey: "nav_today" },
  { path: "/coach", icon: Sparkles, labelKey: "nav_coach" },
  { path: "/chat", icon: MessageSquare, labelKey: "nav_chat" },
  { path: "/workout", icon: Dumbbell, labelKey: "nav_train" },
  { path: "/shopping", icon: ShoppingCart, labelKey: "nav_list" },
  { path: "/profile", icon: User, labelKey: "nav_profile" },
];

const TAB_ROOTS = ["/", "/coach", "/chat", "/workout", "/shopping", "/profile"];

export default function AppLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const { t } = useLang();
  const isSubScreen = !TAB_ROOTS.includes(location.pathname);
  const tabCache = useRef({});

  // Find the nav tab that owns a given pathname (longest matching nav prefix).
  const ownerFor = (pathname) => {
    let owner = null;
    for (const item of navItems) {
      if (item.path === "/") {
        if (pathname === "/") owner = item;
      } else if (pathname === item.path || pathname.startsWith(item.path + "/")) {
        owner = item;
      }
    }
    return owner;
  };

  // Cache the current subpath under its owning tab whenever the route changes.
  useEffect(() => {
    const owner = ownerFor(location.pathname);
    if (owner) tabCache.current[owner.path] = location.pathname;
  }, [location.pathname]);

  const handleTabClick = (e, path) => {
    // Tapping the already-active tab resets it to its root (scroll to top).
    if (location.pathname === path) {
      e.preventDefault();
      tabCache.current[path] = path;
      window.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }
    // Restore a cached subpath for this tab if one exists.
    const cached = tabCache.current[path];
    if (cached && cached !== path) {
      e.preventDefault();
      navigate(cached);
    }
  };
  const goBack = () => {
    if (window.history.length > 1) navigate(-1);
    else navigate("/");
  };

  return (
    <div className="min-h-screen flex flex-col bg-background">
      {/* Back stack header — only on subpages */}
      {isSubScreen && (
        <div
          className="sticky top-0 z-40 bg-background/80 backdrop-blur-xl border-b border-border"
          style={{ paddingTop: "var(--sa-top)" }}
        >
          <div className="max-w-lg mx-auto flex items-center h-12 px-2">
            <button
              onClick={goBack}
              className="touch-target flex items-center gap-0.5 px-2 py-1.5 -ml-1 rounded-lg text-sm text-muted-foreground hover:text-foreground hover:bg-accent transition-colors select-none"
            >
              <ChevronLeft className="w-5 h-5" strokeWidth={2} />
              <span className="font-medium">{t("nav_back")}</span>
            </button>

          </div>
        </div>
      )}

      <main
        className="flex-1 max-w-lg mx-auto w-full"
        style={{
          paddingTop: isSubScreen ? "0px" : "var(--sa-top)",
          paddingBottom: "calc(5rem + var(--sa-bottom))",
        }}
      >
        <AnimatedOutlet />
      </main>

      {location.pathname !== "/coach" && (
        <div className="fixed right-3 z-50" style={{ bottom: "calc(4rem + var(--sa-bottom) + 0.5rem)" }}>
          <LanguageSwitcher compact />
        </div>
      )}

      <nav
        className="fixed bottom-0 inset-x-0 bg-card/80 backdrop-blur-xl border-t border-border z-50"
        style={{ paddingBottom: "var(--sa-bottom)" }}
      >
        <div className="max-w-lg mx-auto flex items-center justify-around h-16 px-1">
          {navItems.map((item) => {
            const active = location.pathname === item.path;
            return (
              <Link
                key={item.path}
                to={item.path}
                onClick={(e) => handleTabClick(e, item.path)}
                className={`flex flex-col items-center gap-0.5 px-2 py-1.5 rounded-xl transition-colors select-none ${
                  active
                    ? "text-primary"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <item.icon className="w-5 h-5" strokeWidth={active ? 2.5 : 1.5} />
                <span className="text-[9px] font-medium">{t(item.labelKey)}</span>
              </Link>
            );
          })}
        </div>
      </nav>
    </div>
  );
}