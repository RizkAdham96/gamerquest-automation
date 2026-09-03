import json
from pathlib import Path
from social.sources import get_all_content
from social.creative_brain import choose_best_idea
from social.carousel_writer import build_carousel
from social.config import MINIMUM_PUBLISH_SCORE
from social import idea_generator

OUTPUT_FILE=Path("social-output.json")

def save_output(data):
    with OUTPUT_FILE.open("w",encoding="utf-8") as file: json.dump(data,file,ensure_ascii=False,indent=2)

def build_candidate_ideas(content): return idea_generator.generate_ideas(content)

def run():
    content=get_all_content(); print(f"Social content items found: {len(content)}")
    if not content: save_output({"status":"skipped","reason":"no_content"}); return
    try: ideas=build_candidate_ideas(content)
    except Exception as error:
        print(f"AI idea generation failed: {error}"); save_output({"status":"error","reason":"ai_generation_failed","error":str(error)}); return
    print(f"Candidate ideas generated: {len(ideas)}")
    if not ideas: save_output({"status":"skipped","reason":"no_ideas"}); return
    best_idea=choose_best_idea(ideas)
    if not best_idea: save_output({"status":"skipped","reason":"repetitive_or_invalid"}); return
    score=best_idea.get("total_score",0); print(f"Best social idea score: {score}")
    if score<MINIMUM_PUBLISH_SCORE: save_output({"status":"skipped","reason":"low_score","best_score":score}); return
    try: complete_idea=idea_generator.expand_idea(best_idea,content)
    except Exception as error:
        print(f"AI carousel expansion failed: {error}"); save_output({"status":"error","reason":"carousel_expansion_failed","error":str(error)}); return

    # Separate source-grounded verification before anything becomes ready/publishable.
    try: verification=idea_generator.verify_carousel(complete_idea,content)
    except Exception as error:
        print(f"Carousel fact-check failed: {error}"); save_output({"status":"error","reason":"fact_check_failed","error":str(error)}); return
    if not verification["valid"]:
        print(f"Carousel rejected by fact-check: {verification['unsupported_claims']}")
        save_output({"status":"skipped","reason":"unsupported_claims","unsupported_claims":verification["unsupported_claims"],"fact_check_reason":verification["reason"]}); return
    print("Carousel fact-check passed.")

    carousel=build_carousel(complete_idea)
    if not carousel: save_output({"status":"skipped","reason":"invalid_carousel"}); return
    save_output({"status":"ready","fact_checked":True,"carousel":carousel})
    print("Social carousel successfully created."); print(f"Output saved to: {OUTPUT_FILE}")

if __name__=="__main__": run()
