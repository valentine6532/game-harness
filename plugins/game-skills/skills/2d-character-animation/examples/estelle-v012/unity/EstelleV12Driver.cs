using UnityEngine;

// Preview helper for EstelleV12Directions: triggers Attack on both instances every few seconds.
public sealed class EstelleV12Driver : MonoBehaviour
{
    public Animator rightAnimator;
    public Animator leftAnimator;
    public float firstAttack = 1.6f;
    public float interval = 3.2f;
    float nextAttack;

    void Start() => nextAttack = Time.time + firstAttack;

    void Update()
    {
        if (Time.time < nextAttack) return;
        if (rightAnimator != null) rightAnimator.SetTrigger("Attack");
        if (leftAnimator != null) leftAnimator.SetTrigger("Attack");
        nextAttack = Time.time + interval;
    }
}
