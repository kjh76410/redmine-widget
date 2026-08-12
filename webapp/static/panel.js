// 파이썬(App._push_tree)이 호출하는 진입점: {title, tree, favorites} 형태의 데이터를 받아 그린다.
// favorites: ["company:5", "team:12", ...] 형태의 즐겨찾기 키 목록.
let favSet = new Set();

function renderPanel(data) {
    document.getElementById("title").textContent = data.title;
    favSet = new Set(data.favorites || []);
    const container = document.getElementById("tree");
    container.innerHTML = "";
    if (!data.tree || data.tree.length === 0) {
        const empty = document.createElement("div");
        empty.className = "empty";
        empty.textContent = "프로젝트 목록을 불러오는 중이거나 없습니다.";
        container.appendChild(empty);
        return;
    }
    data.tree.forEach((node) => container.appendChild(renderNode(node, 0)));
}

function renderNode(node, depth) {
    const wrap = document.createElement("div");

    const row = document.createElement("div");
    row.className = "row";
    row.style.paddingLeft = (depth * 16 + 8) + "px";

    const hasChildren = node.children && node.children.length > 0;

    const arrow = document.createElement("span");
    arrow.className = "arrow";
    arrow.textContent = hasChildren ? "▸" : "";
    row.appendChild(arrow);

    const label = document.createElement("span");
    label.className = "label";
    label.textContent = node.name;
    row.appendChild(label);

    const favKey = node.source + ":" + node.id;
    const star = document.createElement("span");
    star.className = "star";
    star.textContent = favSet.has(favKey) ? "★" : "☆";
    star.title = favSet.has(favKey) ? "즐겨찾기 해제" : "즐겨찾기 추가";
    star.addEventListener("click", (e) => {
        e.stopPropagation();
        window.pywebview.api
            .toggle_favorite(node.id, node.name, node.url, node.source)
            .then((isFav) => {
                if (isFav) favSet.add(favKey); else favSet.delete(favKey);
                star.textContent = isFav ? "★" : "☆";
                star.title = isFav ? "즐겨찾기 해제" : "즐겨찾기 추가";
            });
    });
    row.appendChild(star);

    const childWrap = document.createElement("div");
    childWrap.className = "children collapsed";
    if (hasChildren) {
        node.children.forEach((c) => childWrap.appendChild(renderNode(c, depth + 1)));
    }

    let expanded = false;
    row.addEventListener("click", (e) => {
        if (hasChildren && e.target === arrow) {
            expanded = !expanded;
            arrow.textContent = expanded ? "▾" : "▸";
            childWrap.classList.toggle("collapsed", !expanded);
            return;
        }
        if (e.target === star) return;
        window.pywebview.api.open_url(node.url);
    });

    wrap.appendChild(row);
    wrap.appendChild(childWrap);
    return wrap;
}
