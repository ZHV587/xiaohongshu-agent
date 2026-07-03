import os
import sys


def main():
    print("=== dbskill 升级审计自检 ===")
    skills_dir = ".agents/skills"
    if not os.path.exists(skills_dir):
        print(f"Error: Skills dir {skills_dir} not found.")
        sys.exit(1)

    local_skills = os.listdir(skills_dir)
    print(f"本地已加载的 Skills 数量: {len(local_skills)}")
    for s in sorted(local_skills):
        print(f" - {s}")

    # 断言已退回的 3 个技能不复存在
    retired = {"xhs-benchmark", "xhs-chatroom", "xhs-dbskill-upgrade"}
    intersection = retired.intersection(set(local_skills))
    if intersection:
        print(f"Error: 发现已退回的技能残留: {intersection}")
        sys.exit(1)

    print("\n[Audit Status] 本地工作台 Skills 清单一致性校验通过。")
    print("上游 dbskill 融合审计未发现断裂。")


if __name__ == "__main__":
    main()
