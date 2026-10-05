import { BookOpen } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../App";

interface Skill {
    name: string;
    description: string;
    uri: string;
}

export default function Skills() {
    const [skills, setSkills] = useState<Skill[]>([]);
    const [active, setActive] = useState<Skill | null>(null);
    const [content, setContent] = useState("");
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        api.get("/skills")
            .then((r) => {
                setSkills(r.data.skills);
                if (r.data.skills[0]) setActive(r.data.skills[0]);
            })
            .catch(() => setError("could not load skills"));
    }, []);

    useEffect(() => {
        if (!active) return;
        api.get(`/skills/${active.name}`)
            .then((r) => setContent(r.data.content ?? ""))
            .catch(() => setContent("(no content)"));
    }, [active]);

    return (
        <div className="max-w-4xl space-y-4" data-testid="skills-page">
            <h1 className="flex items-center gap-2 text-2xl font-bold">
                <BookOpen className="h-5 w-5 text-amber-400" /> Skills
            </h1>
            {error && (
                <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-200">
                    {error}
                </div>
            )}
            <div className="grid grid-cols-3 gap-4">
                <div className="col-span-1 space-y-2" data-testid="skills-list">
                    {skills.length === 0 && (
                        <div className="text-sm text-zinc-400">
                            No skills exposed.
                        </div>
                    )}
                    {skills.map((s) => (
                        <button
                            type="button"
                            key={s.name}
                            onClick={() => setActive(s)}
                            data-testid={`skill-${s.name}`}
                            className={`w-full rounded-lg border px-3 py-2 text-left text-sm ${
                                active?.name === s.name
                                    ? "border-amber-500/40 bg-amber-500/10 text-amber-200"
                                    : "border-zinc-800 text-zinc-300"
                            }`}
                        >
                            <div className="font-medium">{s.name}</div>
                            <div className="mt-0.5 line-clamp-2 text-xs text-zinc-400">
                                {s.description}
                            </div>
                        </button>
                    ))}
                </div>
                <div className="col-span-2">
                    <pre
                        data-testid="skill-content"
                        className="max-h-[60vh] overflow-auto whitespace-pre-wrap rounded-xl border border-zinc-800 bg-zinc-900/40 p-4 text-sm text-zinc-200"
                    >
                        {content || "Select a skill…"}
                    </pre>
                </div>
            </div>
        </div>
    );
}
